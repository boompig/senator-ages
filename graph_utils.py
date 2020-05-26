from matplotlib import pyplot as plt
from typing import List


plt.rcParams['figure.dpi'] = 200


def graph_age_histogram(df, title: str, age_col: str, y_axis_label='# Senators') -> List[dict]:
    date_ranges = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 100)]
    hist_rows = []

    xs = ['under 40', '40 - 49', '50 - 59', '60 - 69', '70+']
    ys = []

    for x_label, (min_inc, max_excl) in zip(xs, date_ranges):
        num_senators = ((df[age_col] >= min_inc) & (df[age_col] < max_excl)).sum()
        hist_rows.append({
            'age_range': x_label,
            'num_senators': num_senators,
        })
        ys.append(num_senators)

    plt.bar(x=xs, height=ys)
    plt.title(title)
    plt.ylabel(y_axis_label)
    plt.xlabel('Age')
    plt.show()

    return hist_rows
