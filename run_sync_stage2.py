from pipeline.config import load_settings
from pipeline import phase3c,himawari as hw
result=phase3c.synchronized_2016(load_settings())
hw.json_write('outputs/stages/stage2_sync.json',result)
print('2016 result',result,flush=True)
