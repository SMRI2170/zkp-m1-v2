"""Independent GhostBuster Eq.2-6 implementation on observable RSS and claims.

No true transmitter location, actual power, attack label or scenario seed is an
argument to localization. This implements known/modelled nominal power LDPL;
it is NOT the earlier joint unknown-power MLAT detector.
"""
from itertools import combinations
import numpy as np


def ranges_from_rss(rss, intercept, exponent):
    if not np.isfinite(exponent) or exponent <= 0:
        raise ValueError('Positive LDPL exponent required')
    rss = np.asarray(rss, dtype=float)
    return 10. ** ((np.asarray(intercept) - rss) / (10. * exponent))


def _lm(positions, ranges, start, iterations=70):
    """Batched constrained range-NLSE; deterministic, claim-independent starts.

    Bounds describe this synthetic surveillance domain, not a claimed position.
    Residuals are in metres. No random noise is added a second time in NLSE.
    """
    x = start.copy()
    low = np.array([-2000., -2000., 2.001])
    high = np.array([2500., 2500., 2000.])
    x = np.clip(x, low, high)
    damping = np.full(len(x), .01)
    cost_converged = np.zeros(len(x), dtype=bool)
    for _ in range(iterations):
        delta = x[:, None, :] - positions
        distance = np.maximum(np.linalg.norm(delta, axis=-1), 1.e-9)
        residual = distance - ranges
        jacobian = delta / distance[..., None]
        gradient = np.einsum('bsi,bs->bi', jacobian, residual)
        hessian = np.einsum('bsi,bsj->bij', jacobian, jacobian)
        matrix = hessian + damping[:, None, None] * np.eye(3)
        step = np.linalg.solve(matrix, gradient[..., None])[..., 0]
        candidate = np.clip(x - step, low, high)
        cost = (residual ** 2).sum(axis=1)
        new_cost = ((np.linalg.norm(candidate[:, None, :] - positions, axis=-1) - ranges) ** 2).sum(axis=1)
        accepted = new_cost < cost
        actual_reduction = cost - new_cost
        effective_step = x - candidate
        linear_residual = residual - np.einsum('bsi,bi->bs', jacobian, effective_step)
        predicted_reduction = cost - (linear_residual ** 2).sum(axis=1)
        # Standard least-squares ftol termination, independently checked against
        # scipy.optimize.least_squares below. This is not an alarm threshold.
        adequate_model = (predicted_reduction > 1.e-12) & (actual_reduction > .25*predicted_reduction)
        cost_converged |= accepted & adequate_model & (actual_reduction < 1.e-10*(1+cost))
        x[accepted] = candidate[accepted]
        damping = np.clip(damping * np.where(accepted, .3, 5.), 1.e-9, 1.e12)
    delta = x[:, None, :] - positions
    distance = np.maximum(np.linalg.norm(delta, axis=-1), 1.e-9)
    residual = distance - ranges
    gradient = np.einsum('bsi,bs->bi', delta / distance[..., None], residual)
    projected = x - np.clip(x - gradient, low, high)
    stationary = (np.linalg.norm(projected, axis=1) < 1.e-3) | cost_converged
    return x, (residual ** 2).sum(axis=1), stationary


def locate_frames(ranges, receivers, subset_size=4, iterations=70):
    """Eq.3 all size-s combinations, Eq.4 coordinate-wise median.

    Returns estimates and solver diagnostics. Nonfinite input is never imputed.
    Three non-collinear ground receivers are a minimum for the range solver;
    our multi-observer protocol explicitly requires >=4 received values.
    """
    ranges = np.asarray(ranges, float)
    receivers = np.asarray(receivers, float)
    if ranges.ndim != 2 or receivers.shape != (ranges.shape[1], 3):
        raise ValueError('Expected frames x receivers and receivers x 3')
    if len(receivers) < 4 or subset_size < 4 or subset_size > len(receivers):
        raise ValueError('Multi-observer evaluation requires >=4 receivers')
    if not np.isfinite(ranges).all() or (ranges <= 0).any() or not np.isfinite(receivers).all():
        raise ValueError('Finite positive ranges required')
    indices = np.array(list(combinations(range(len(receivers)), subset_size)))
    subset_positions = receivers[indices]
    # Collinear configurations have a non-unique 3D solution even with known P.
    ranks = np.array([np.linalg.matrix_rank(p - p.mean(axis=0), tol=1.e-8) for p in subset_positions])
    if (ranks < 2).any():
        raise ValueError('Collinear receiver subset: declare a different layout')
    points = np.broadcast_to(subset_positions, (len(ranges),) + subset_positions.shape).reshape(-1, subset_size, 3)
    values = ranges[:, indices].reshape(-1, subset_size)
    estimates, costs, stationary = [], [], []
    # Two starts, independent of claims/truth. Retain minimum range residual;
    # no branch is chosen using the claimed position.
    for height in (60., 300.):
        x = points.mean(axis=1)
        x[:, 2] = height
        chunks = [_lm(points[i:i+4096], values[i:i+4096], x[i:i+4096], iterations)
                  for i in range(0, len(x), 4096)]
        estimates.append(np.concatenate([c[0] for c in chunks]))
        costs.append(np.concatenate([c[1] for c in chunks]))
        stationary.append(np.concatenate([c[2] for c in chunks]))
    choice = costs[1] < costs[0]
    best = np.where(choice[:, None], estimates[1], estimates[0])
    solved = np.where(choice, stationary[1], stationary[0])
    # Do not convert a limited batched optimizer budget into a claimed RF
    # limitation. Retry its unfinished fits with the independent SciPy TRF
    # implementation, using the same residual, bounds and claim-free start.
    # Failed reference fits remain explicitly unsolved.
    unfinished = np.flatnonzero(~solved)
    best_cost = np.minimum(costs[0], costs[1])
    if len(unfinished):
        from scipy.optimize import least_squares
        for i in unfinished:
            result = least_squares(
                lambda x: np.linalg.norm(x-points[i], axis=1)-values[i], best[i],
                bounds=([-2000.,-2000.,2.001],[2500.,2500.,2000.]),
                max_nfev=500,ftol=1.e-10,xtol=1.e-10,gtol=1.e-8)
            if result.success and np.isfinite(result.x).all():
                best[i] = result.x
                best_cost[i] = 2*result.cost
                solved[i] = True
    best = best.reshape(len(ranges), len(indices), 3)
    solved = solved.reshape(len(ranges), len(indices))
    # Numerical-failure policy is our explicit addition: use only stationary
    # fits, require >=80% of all declared combinations, otherwise abstain.
    # Report every omitted fit; never present omission as measured outlier data.
    eligible = solved.sum(axis=1) >= np.ceil(.8 * len(indices))
    median = np.full((len(ranges), 3), np.nan)
    for i in np.flatnonzero(eligible):
        median[i] = np.median(best[i, solved[i]], axis=0)
    return median, dict(
        subset_count=len(indices), fit_count=len(values),
        scipy_fallback_fits=len(unfinished),
        nonstationary_fits=int((~solved).sum()),
        frame_stationary=eligible,
        range_residual_rms_m=np.sqrt(best_cost / subset_size))


def window_scores(rss, claims, receivers, intercept, exponent, subset_size=4, iterations=70):
    """RSS [windows,N,K], claims [windows,N,3], normal-only model parameters.

    Missing a required RSS in a window produces NaN/UND. Single observer uses
    Eq.6, never returns a 3D position. Multiple observers use Eq.5.
    """
    rss = np.asarray(rss, float)
    claims = np.asarray(claims, float)
    receivers = np.asarray(receivers, float)
    if rss.ndim != 3 or claims.shape != rss.shape[:2] + (3,) or receivers.shape != (rss.shape[2], 3):
        raise ValueError('Invalid observation shapes')
    if not np.isfinite(claims).all():
        raise ValueError('Received claims must be finite')
    good = np.isfinite(rss).all(axis=(1, 2))
    scores = np.full(len(rss), np.nan)
    diagnostic = dict(total_windows=len(rss), complete_windows=int(good.sum()), subset_count=0, fit_count=0, nonstationary_fits=0)
    if not good.any():
        return scores, diagnostic
    ranges = ranges_from_rss(rss[good], intercept, exponent)
    if len(receivers) == 1:
        reported = np.linalg.norm(claims[good] - receivers[0], axis=-1)
        scores[good] = np.median(np.abs(ranges[..., 0] - reported), axis=1)
    else:
        estimate, detail = locate_frames(ranges.reshape(-1, len(receivers)), receivers, subset_size, iterations)
        n = rss.shape[1]
        # Eq.5: median of per-message Euclidean errors, NOT error of averaged
        # moving positions, and NOT a median of dB RSS before ranging.
        errors = np.linalg.norm(estimate.reshape(-1, n, 3) - claims[good], axis=-1)
        valid = detail.pop('frame_stationary').reshape(-1, n).all(axis=1)
        indices = np.flatnonzero(good)
        scores[indices[valid]] = np.median(errors[valid], axis=1)
        detail.pop('range_residual_rms_m')
        diagnostic.update(detail)
    diagnostic['scored_windows'] = int(np.isfinite(scores).sum())
    return scores, diagnostic


def normal_threshold(scores, policy, role):
    if role != 'calibrate_normal':
        raise ValueError('Only independent normal calibration is permitted')
    values = np.asarray(scores, float)
    values = values[np.isfinite(values)]
    if not len(values):
        raise ValueError('No normal scores; cannot set a threshold')
    if policy == 'max_normal':
        return float(values.max())
    if policy == 'q95_normal':
        return float(np.quantile(values, .95, method='higher'))
    raise ValueError('Unknown threshold policy')
