from __future__ import annotations
import asyncio
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.config import RunOptions
from app.job_store import JobState
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.workbook import WorkbookParser

async def run(input_path: Path):
    parser=WorkbookParser(); inspection=parser.inspect(input_path)
    assert inspection.estimated_records > 0
    run_dir=ROOT/'runs'/'_smoke_test'; run_dir.mkdir(parents=True,exist_ok=True)
    job=JobState(job_id='_smoke_test',run_dir=run_dir)
    await run_pipeline(job,input_path,'',RunOptions(max_leads=5,demo_mode=True,concurrency=2))
    assert job.status == 'completed', job.error
    assert (run_dir/'output/final_leads.csv').exists()
    assert (run_dir/'output/final_leads.xlsx').exists()
    assert len(job.leads) == 5
    print('SMOKE PASS',job.summary)

if __name__=='__main__':
    if len(sys.argv)<2: raise SystemExit('usage: python tests/smoke_test.py <xlsx-or-csv>')
    asyncio.run(run(Path(sys.argv[1])))
