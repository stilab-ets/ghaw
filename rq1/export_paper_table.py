"""Export the paper's descriptive table from recomputed per-file measurements."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.labels import ROOT, save, write_csv


def main():
    frame = pd.read_csv(ROOT / 'rq1/output/rq1_per_file_metrics.csv')
    fields = [('Size and structure', 'Body lines', 'body_lines'),
              ('Size and structure', 'Frontmatter lines', 'frontmatter_lines'),
              ('Size and structure', 'Code block lines', 'code_block_lines')]
    fields += [('Heading levels', f'H{x}', f'h{x}_count') for x in range(1, 6)]
    fields += [('Prose and readability', name, field) for name, field in
               [('Body words', 'body_word_count'), ('Sentences', 'sentence_count'),
                ('Syllables', 'readability_syllable_count'), ('Pictographic symbols', 'status_symbol_count'),
                ('Flesch Reading Ease', 'flesch_reading_ease')]]
    rows = []
    for group, name, field in fields:
        values = frame[field].dropna()
        rows.append(dict(group=group, metric=name, min=float(values.min()), mean=float(values.mean()),
                         median=float(values.median()), max=float(values.max())))
    write_csv(ROOT / 'rq1/output/paper_table.csv', rows)
    symbols = frame.status_symbol_count.gt(0)
    headings = frame[[f'h{x}_count' for x in range(1, 7)]].sum().sum()
    claims = dict(symbol_files=int(symbols.sum()), symbol_percent=100 * float(symbols.mean()),
                  heading_total=int(headings), h2_h3_percent=100 * (frame.h2_count.sum() + frame.h3_count.sum()) / headings,
                  lists_percent=100 * float((frame.bullet_list_count + frame.ordered_list_count).gt(0).mean()),
                  code_blocks_percent=100 * float(frame.code_block_count.gt(0).mean()),
                  templates_percent=100 * float(frame.template_expression_count.gt(0).mean()),
                  fre_below_60_percent=100 * float(frame.flesch_reading_ease.dropna().lt(60).mean()))
    save(ROOT / 'rq1/output/text_results.json', claims)
    print('RQ1 paper table and text statistics exported.')


if __name__ == '__main__':
    main()
