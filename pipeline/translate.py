"""Bilingual, honest display rules. Thresholds are configurable and provisional."""
from datetime import datetime,timezone
import math

DEFAULTS=dict(risk_probability_min=[0,.2,.4,.6,.8],risk_ratio_min=[0,.5,1,1.5,2],
              intensity_mw=[10,100,1000],confidence_min=[.5,.8],trend_relative_change=.2)
WORDS={
 'en':dict(risk=['Very low','Low','Moderate','High','Very high'],intensity=['Low observed power','Moderate observed power','High observed power','Very high observed power'],
           confidence=['Low confidence','Moderate confidence','High confidence'],trend=['Dying down','Stable','Spreading'],
           unknown='Awaiting data',last='Last seen',confirmed='Confirmed by',satellite='satellite',satellites='satellites',
           notes=['Satellite heat detections do not confirm a fire or its cause.',
                  'FRP is observed heat power, not burned area, damage or fire-front spread.',
                  'Clouds and observation gaps can hide fires; forecasts are probabilities, not certainties.']),
 'bn':dict(risk=['খুব কম','কম','মাঝারি','উচ্চ','খুব উচ্চ'],intensity=['পর্যবেক্ষিত তাপশক্তি কম','পর্যবেক্ষিত তাপশক্তি মাঝারি','পর্যবেক্ষিত তাপশক্তি বেশি','পর্যবেক্ষিত তাপশক্তি খুব বেশি'],
           confidence=['কম আস্থা','মাঝারি আস্থা','উচ্চ আস্থা'],trend=['কমে আসছে','স্থিতিশীল','ছড়িয়ে পড়ছে'],
           unknown='তথ্য আসার অপেক্ষায়',last='শেষ দেখা গেছে',confirmed='শনাক্তকরণ সমর্থন করেছে',satellite='টি উপগ্রহ',satellites='টি উপগ্রহ',
           notes=['উপগ্রহে তাপ শনাক্ত হলেই আগুন বা তার কারণ নিশ্চিত হয় না।',
                  'FRP হলো পর্যবেক্ষিত তাপশক্তি; পোড়া এলাকা, ক্ষয়ক্ষতি বা আগুনের অগ্রভাগের বিস্তার নয়।',
                  'মেঘ ও পর্যবেক্ষণের বিরতিতে আগুন আড়াল হতে পারে; পূর্বাভাস সম্ভাবনা, নিশ্চয়তা নয়।'])}


def settings(cfg=None):return {**DEFAULTS,**((cfg or {}).get('translation',{}))}


def probability(value):
    if value is None:return None
    value=float(value)
    if not math.isfinite(value) or not 0<=value<=1:raise ValueError('Probability must be finite and within [0,1]')
    return value


def risk_level(p,p_clim,cfg=None):
    p,p_clim=probability(p),probability(p_clim)
    if p is None or p_clim is None or p_clim==0:return None,None
    ratio=p/p_clim;rule=settings(cfg);level=0
    for i,(pm,rm) in enumerate(zip(rule['risk_probability_min'],rule['risk_ratio_min'])):
        if (p>=pm or math.isclose(p,pm,rel_tol=0,abs_tol=1e-12)) and (ratio>=rm or math.isclose(ratio,rm,rel_tol=0,abs_tol=1e-12)):level=i
    return level,ratio


def intensity_class(frp,cfg=None):
    if frp is None:return None
    frp=float(frp)
    if not math.isfinite(frp) or frp<0:raise ValueError('FRP must be finite and nonnegative')
    return sum(frp>=t for t in settings(cfg)['intensity_mw'])


def confidence_class(value,cfg=None):
    value=probability(value)
    return None if value is None else sum(value>=t for t in settings(cfg)['confidence_min'])


def trend_class(last_overpasses,cfg=None):
    if len(last_overpasses)<3:return None
    values=[float(v) for v in last_overpasses[-3:]]
    if not all(math.isfinite(v) and v>=0 for v in values):raise ValueError('Overpass FRP must be finite and nonnegative')
    first,last=values[0],values[-1];threshold=settings(cfg)['trend_relative_change']
    if first==0:return 2 if last>0 else 1
    delta=last-first
    if delta>=first*threshold:return 2
    if delta<=-first*threshold:return 0
    return 1


def utc(value):
    if value is None:return None
    if not isinstance(value,datetime):value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def translate(p=None,p_clim=None,frp_mw=None,last_overpasses=(),confidence=None,last_seen=None,satellites=(),now=None,cfg=None):
    level,ratio=risk_level(p,p_clim,cfg);intensity=intensity_class(frp_mw,cfg);trend=trend_class(last_overpasses,cfg);conf=confidence_class(confidence,cfg)
    n=len(set(satellites));seen=utc(last_seen);snapshot=utc(now)
    if seen is not None and snapshot is not None and seen>snapshot:seen=None
    result=dict(risk_level=None if level is None else level+1,probability=p,climatology_probability=p_clim,probability_ratio=ratio,
                n_satellites=n,trend_basis='last three comparable overpasses; power trend, not measured fire-front motion',status='provisional display rules')
    for lang,w in WORDS.items():
        result[lang]=dict(risk=w['unknown'] if level is None else w['risk'][level],
                         intensity=w['unknown'] if intensity is None else w['intensity'][intensity],
                         trend=w['unknown'] if trend is None else w['trend'][trend],
                         confidence=w['unknown'] if conf is None else w['confidence'][conf],
                         last_seen=w['unknown'] if seen is None else f"{w['last']}: {seen.isoformat()} (UTC)",
                         satellite_confirmation=(f"{w['confirmed']} {n} {w['satellite'] if n==1 else w['satellites']}"),
                         honesty_notes=list(w['notes']),
                         trend_basis=('Observed power trend, not measured fire-front motion' if lang=='en' else 'পর্যবেক্ষিত তাপশক্তির প্রবণতা; আগুনের অগ্রভাগের মাপা গতি নয়'),
                         status=('Provisional display rules' if lang=='en' else 'প্রাথমিক প্রদর্শন বিধি'))
    return result
