"""Run the publication analyses offline and verify the numerical outputs."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMANDS = [
    ['rq1/analyze_rq1.py'],
    ['rq1/export_paper_table.py'],
    ['rq1/generate_heading_wordcloud.py', '--content-focused'],
    ['rq2/analyze_rq2.py'],
    ['rq2/analyze_maintenance_periods.py'],
    ['rq3/compute_rq3_results.py'],
    ['rq4/calculate_rq4_agreement.py'],
    ['verification/verify_results.py'],
]


if __name__ == '__main__':
    (ROOT / 'figures').mkdir(exist_ok=True)
    for args in COMMANDS:
        print('Running:', ' '.join(args), flush=True)
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    print('All analyses completed and numerical verification passed.')
