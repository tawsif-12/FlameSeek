import asyncio
import json
from datetime import date,timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import memory,place_pipeline
from schemas import FireMemoryRequest


def request(**kwargs):
    return FireMemoryRequest(aoi={'bbox':[88,20,93,27],'name':'Bangladesh'},history_years=5,sensors=['modis','viirs_snpp'],**kwargs)


def test_saved_memory_is_exact_query_and_preserves_dates(monkeypatch):
    payload=request();calls=[]
    end=memory.datetime.now(memory.timezone.utc).date()-timedelta(days=3)
    key=memory.memory_cache_key(payload,memory.history_start(end,5),end)
    saved={'period':{'end':end.isoformat(),'start':'2021-11-02'},'provenance':{}}
    def read(namespace,candidate,*args):
        calls.append(candidate)
        return json.dumps(saved) if candidate==key else None
    monkeypatch.setattr(memory,'disk_read',read)
    result=memory.saved_memory(payload)
    assert result['period']==saved['period']
    assert result['provenance']['saved_preview'] is True
    assert len(calls)<=8
    assert memory.saved_memory(request(comparison_window_days=60)) is None


def test_explicit_date_and_refresh_never_fall_back_to_older_dates(monkeypatch):
    calls=[]
    monkeypatch.setattr(memory,'disk_read',lambda *args:(calls.append(args) or None))
    assert memory.saved_memory(request(end_date=date(2025,1,1))) is None
    assert len(calls)==1
    calls.clear()
    assert memory.saved_memory(request(refresh=True)) is None and not calls


def test_saved_endpoints_never_start_background_jobs(monkeypatch):
    def fail(*args,**kwargs):raise AssertionError('Saved preview must not download or start analysis')
    monkeypatch.setattr(memory,'start_job',fail)
    monkeypatch.setattr(place_pipeline,'start_job',fail)
    monkeypatch.setattr(memory,'disk_read',lambda *args:None)
    monkeypatch.setattr(place_pipeline,'disk_read',lambda *args:None)
    app=FastAPI();app.include_router(memory.router,prefix='/api');app.include_router(place_pipeline.router,prefix='/api')
    client=TestClient(app)
    for path in ['fire_memory','place_pipeline']:
        response=client.post('/api/'+path+'/saved',json=request().model_dump(mode='json'))
        assert response.status_code==200 and response.json()=={'result':None}


def test_raw_pipeline_mode_does_not_parse_csv(monkeypatch):
    import firms_client as fc
    async def available():return {}
    async def fetch(*args):return 'latitude,longitude\n1,2\n','MODIS_SP'
    def parse(*args):raise AssertionError('Raw-only pipeline should not parse discarded rows')
    monkeypatch.setattr(fc,'load_availability',available)
    monkeypatch.setattr(fc,'_fetch_csv',fetch)
    monkeypatch.setattr(fc,'_parse_csv',parse)
    sink=[]
    rows,report=asyncio.run(fc.fetch_hotspots_with_report((88,20,93,27),date(2024,1,1),date(2024,1,2),['modis'],raw_sink=sink,parse_rows=False))
    assert rows==[] and report['failed_chunks']==[] and sink==[('MODIS_SP','latitude,longitude\n1,2\n')]
