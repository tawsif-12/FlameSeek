import pytest
from pipeline import translate as t


@pytest.mark.parametrize('level,p,baseline',[(0,0,.4),(1,.2,.4),(2,.4,.4),(3,.6,.4),(4,.8,.4)])
def test_risk_thresholds_are_inclusive(level,p,baseline):
    assert t.risk_level(p,baseline)[0]==level
    if level>0:assert t.risk_level(p-1e-8,baseline)[0]<level


@pytest.mark.parametrize('level,ratio',[(1,.5),(2,1.),(3,1.5),(4,2.)])
def test_risk_ratio_boundaries(level,ratio):
    p=min(.9,ratio*.8)
    assert t.risk_level(p,p/ratio)[0]==level
    assert t.risk_level(p,p/(ratio-1e-8))[0]<level


@pytest.mark.parametrize('value,expected',[(0,0),(9.999999,0),(10,1),(99.99999,1),(100,2),(999.9999,2),(1000,3)])
def test_intensity_boundaries(value,expected):assert t.intensity_class(value)==expected


@pytest.mark.parametrize('value,expected',[(0,0),(.499999,0),(.5,1),(.799999,1),(.8,2),(1,2)])
def test_confidence_boundaries(value,expected):assert t.confidence_class(value)==expected


@pytest.mark.parametrize('values,expected',[([100,110,120],2),([100,110,119.9999],1),([100,90,80],0),([100,90,80.0001],1),([0,0,0],1),([0,0,1],2),([1,2],None)])
def test_trend_boundaries_and_missing(values,expected):assert t.trend_class(values)==expected


def test_unknown_inputs_do_not_create_forecast_or_risk():
    assert t.risk_level(None,.1)==(None,None)
    assert t.risk_level(.9,0)==(None,None)
    for invalid in [-1,1.1,float('nan')]:
        with pytest.raises(ValueError):t.risk_level(invalid,.2)
    with pytest.raises(ValueError):t.intensity_class(-1)


def test_bilingual_notes_last_seen_and_satellite_deduplication():
    result=t.translate(frp_mw=100,confidence=.9,last_seen='2026-11-02T07:00Z',now='2026-11-02T23:59Z',satellites=['Aqua','S-NPP','Aqua'])
    assert result['n_satellites']==2 and result['risk_level'] is None
    for language in ['en','bn']:
        assert len(result[language]['honesty_notes'])==3
        assert '2026-11-02' in result[language]['last_seen']
        assert all('???' not in value for value in result[language].values() if isinstance(value,str))
    assert result['bn']['risk']!=result['en']['risk']
