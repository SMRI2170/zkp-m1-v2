"""Proof by construction: arbitrary per-frame transmit power makes distance non-identifiable.
This is synthetic mathematics, not an RF measurement. Stdlib only.
"""
import math
import random

seed = 20261101
random.seed(seed)
N = 1000
n = 2.0
max_difference = 0.0
for k in range(N):
    d_true = 10 ** random.uniform(math.log10(5), math.log10(150))
    d_other = 4.0 * d_true
    a_true = -42.0 + random.gauss(0, 5)
    a_other = a_true + 10*n*math.log10(d_other/d_true)
    observed_1 = a_true - 10*n*math.log10(d_true)
    observed_2 = a_other - 10*n*math.log10(d_other)
    max_difference = max(max_difference, abs(observed_1 - observed_2))

assert max_difference < 1e-10
print(f'{N} distinct asynchronous events: max RSSI difference={max_difference:.3g} dB')
print(f'Each alternative distance is x4, compensated by +{10*n*math.log10(4):.4f} dB in reference power')
print('Result: distance cannot be identified from these RSSI observations alone.')
