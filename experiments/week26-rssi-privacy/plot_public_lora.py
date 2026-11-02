"""Aggregate-only plots: never draw/export raw trajectories or coordinates."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('result', type=Path)
    args = p.parse_args()
    d = json.loads((args.result / 'summary.json').read_text())
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.dpi': 180})
    colors = ['#173f73', '#008786', '#b35d27']

    def save(fig, name, note):
        fig.text(.5, .015, note, ha='center', fontsize=9, color='#444444')
        fig.tight_layout(rect=(0, .065, 1, .96))
        for ext in ['png', 'svg']:
            fig.savefig(args.result / f'{name}.{ext}')
        plt.close(fig)

    normal = [r for r in d['window'] if r['radial_range_shift_m'] == 0]
    x = np.arange(3)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))
    ax[0].bar(x - .18, [r['mae_m'] for r in normal], width=.36, color=colors[0], label='RSSI log-distance')
    ax[0].bar(x + .18, [r['prior_mae_m'] for r in normal], width=.36, color='#aab6c5', label='Training median range')
    ax[0].set(xticks=x, xticklabels=['1 packet', '5 packets', '20 packets'], ylabel='Mean absolute range error (m)', ylim=(0, 45))
    ax[0].legend(fontsize=9)
    ax[0].set_title('Median aggregation helps only modestly')
    for shift, color in zip([0, 30, 100], colors):
        rows = [r for r in d['window'] if r['radial_range_shift_m'] == shift and not r['compensated']]
        ax[1].plot(x, [100 * r['alarm_fraction'] for r in rows], marker='o', color=color,
                   label='Normal / false alarm' if shift == 0 else f'Injected range +{shift} m')
    ax[1].set(xticks=x, xticklabels=['1 packet', '5 packets', '20 packets'], ylabel='Alarm rate (%)', ylim=(0, 100))
    ax[1].legend(fontsize=9)
    ax[1].set_title('Injected claims; observed RSSI unchanged')
    save(fig, 'lora-window-and-baseline', 'Public LoRa UAV-receiver data | 48 run-held-out folds | macro means | flat-terrain range proxy')

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.4))
    delay = d['delay']
    t = [r['requested_delay_s'] for r in delay]
    ax[0].plot(t, [r['mae_m'] for r in delay], 'o-', color=colors[0])
    ax[0].set(xlabel='Requested age of RSSI (s)', ylabel='Mean absolute range error (m)', ylim=(0, 65))
    ax[1].plot(t, [100 * r['normal_fpr'] for r in delay], 'o-', color=colors[2])
    ax[1].axhline(5, color='#888888', linestyle='--', label='Calibration target: 5%')
    ax[1].set(xlabel='Requested age of RSSI (s)', ylabel='Normal false-alarm rate (%)', ylim=(0, 30))
    ax[1].legend(fontsize=9)
    fig.suptitle('Pairing older measured RSSI with current range')
    save(fig, 'lora-pairing-delay', 'Same query cohort for all delays | past packets only | threshold calibrated on current RSSI | no attack')

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.4))
    for k, color in zip([1, 5, 20], colors):
        rows = [r for r in d['dropout'] if r['window_packets'] == k]
        drop = [100 * r['drop_fraction'] for r in rows]
        label = f'{k} packet' + ('s' if k != 1 else '')
        ax[0].plot(drop, [r['span_median_s'] for r in rows], 'o-', color=color, label=label)
        ax[1].plot(drop, [100 * r['processed_original_packet_fraction'] for r in rows], 'o-', color=color, label=label)
    ax[0].set(xlabel='Additional synthetic random deletion (%)', ylabel='Median block time span (s)')
    ax[1].set(xlabel='Additional synthetic random deletion (%)', ylabel='Original packets used in full blocks (%)', ylim=(0, 105))
    for a in ax:
        a.legend(fontsize=9)
    fig.suptitle('Thinning packets that were already received')
    save(fig, 'lora-additional-dropout', '10 thinning seeds per fold | no block across >2 s gap | not an estimate of original RF packet-loss rate')

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for delta, style in [(30, '--'), (100, '-')]:
        for compensation, color in [(False, colors[0]), (True, colors[2])]:
            rows = [r for r in d['window'] if r['radial_range_shift_m'] == delta and r['compensated'] == compensation]
            label = f'+{delta} m, ' + ('model power compensation' if compensation else 'unchanged RSSI')
            ax.plot(x, [100 * r['alarm_fraction'] for r in rows], marker='o', linestyle=style, color=color, label=label)
    ax.plot(x, [100 * r['normal_fpr'] for r in normal], 'kx', markersize=9, label='Normal false alarm')
    ax.set(xticks=x, xticklabels=['1 packet', '5 packets', '20 packets'], ylabel='Alarm rate (%)', ylim=(0, 100))
    ax.legend(fontsize=9, loc='upper left')
    ax.set_title('Model-compensated power changes preserve the normal score')
    save(fig, 'lora-power-counterexample', 'Real RSSI baseline + synthetic block-level claim/power changes | unbounded model compensation | not a flown attack')


if __name__ == '__main__':
    main()
