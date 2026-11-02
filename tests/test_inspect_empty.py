from pipeline.inspect_raw import inspect_firms


def test_empty_window_extract_is_reported_without_mutation(tmp_path):
    path=tmp_path/'modis_empty.csv'
    path.write_text('latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n')
    before=path.read_bytes()
    lines,facts=inspect_firms(tmp_path)
    assert facts['files'][path.name]['rows']==0
    assert 'empty window extraction' in '\n'.join(lines)
    assert path.read_bytes()==before
