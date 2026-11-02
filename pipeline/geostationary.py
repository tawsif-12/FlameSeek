"""One nominal geostationary source per common-grid cell, chosen by VZA."""
import numpy as np
import pandas as pd
from pipeline import himawari as hw


def assign(longitude, latitude, cfg):
    lon,lat=np.broadcast_arrays(np.asarray(longitude,float),np.asarray(latitude,float))
    platforms=cfg['geostationary']['platforms']
    names=list(platforms)
    angles=np.stack([hw.view_zenith(lon,lat,p['sub_lon_deg'],sat_alt_m=cfg['geostationary']['altitude_m']) for p in platforms.values()],axis=-1)
    finite=np.isfinite(lon)&np.isfinite(lat)&(abs(lat)<=90)&(abs(lon)<=180)
    eligible=np.where(np.isfinite(angles)&(angles<cfg['geostationary']['max_vza_deg'])&finite[...,None],angles,np.inf)
    index=np.argmin(eligible,axis=-1)
    minimum=np.min(eligible,axis=-1)
    chosen=np.asarray(names,dtype=object)[index]
    chosen=np.where(np.isfinite(minimum),chosen,None)
    return chosen,np.where(np.isfinite(minimum),minimum,np.nan),angles


def plot(cfg):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    # Display every 0.1-degree cell across South/East Asia, including cells without fires.
    west,south,east,north=[40,-15,155,55]; deg=cfg['grid']['cell_deg']
    lon=np.arange(west+deg/2,east,deg); lat=np.arange(south+deg/2,north,deg)
    lo,la=np.meshgrid(lon,lat)
    chosen,_,_=assign(lo,la,cfg)
    names=list(cfg['geostationary']['platforms'])
    values=np.zeros(chosen.shape,int)
    for i,name in enumerate(names,1): values[chosen==name]=i
    fig,ax=plt.subplots(figsize=(12,6))
    image=ax.imshow(values,origin='lower',extent=[west,east,south,north],aspect='auto',interpolation='nearest',
                    cmap=ListedColormap(['#dddddd','#4393c3','#e6a23c']),norm=BoundaryNorm([-.5,.5,1.5,2.5],3))
    bar=fig.colorbar(image,ax=ax,ticks=[0,1,2],shrink=.8); bar.ax.set_yticklabels(['No valid view',*names])
    # Offline Natural Earth boundaries are optional; no cartographic downloads.
    for name,(w,s,e,n) in cfg['himawari']['regions'].items():
        ax.plot([w,e,e,w,w],[s,s,n,n,s],color='black',lw=.8)
        if name!='full_IGP': ax.text((w+e)/2,n+.5,name,ha='center',fontsize=7)
    for name,p in cfg['geostationary']['platforms'].items():
        ax.plot(p['sub_lon_deg'],0,'k+',ms=8); ax.text(p['sub_lon_deg'],2,name,ha='center',fontsize=8)
    ax.set(xlabel='Longitude',ylabel='Latitude',title='Geostationary assignment: minimum VZA below 65° (nominal geometry)')
    fig.tight_layout(); path=cfg['paths']['figures_dir']/'geo_platform_assignment.png'
    fig.savefig(path,dpi=150,bbox_inches='tight'); plt.close(fig)
    return path


def write_global_assignment(cfg):
    """Stream the complete common degree grid; no fire-data selection of cells."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pipeline.grid import cell_id
    deg=cfg['grid']['cell_deg']; nx=int(round(360/deg)); ny=int(round(180/deg))
    path=cfg['paths']['window_processed']/'geo_platform_assignment.parquet'
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp.parquet')
    writer=None; total=0; counts={}
    try:
        for row0 in range(0,ny,50):
            iy,ix=np.meshgrid(np.arange(row0,min(row0+50,ny)),np.arange(nx),indexing='ij')
            ix,iy=ix.ravel(),iy.ravel()
            lon=-180+(ix+.5)*deg; lat=-90+(iy+.5)*deg
            chosen,minimum,angles=assign(lon,lat,cfg)
            frame=pd.DataFrame(dict(cell_id=cell_id(ix,iy),lon=lon.astype('float32'),lat=lat.astype('float32'),
                                    geo_platform=pd.array(chosen,dtype='string'),geo_vza_deg=minimum.astype('float32')))
            for i,name in enumerate(cfg['geostationary']['platforms']): frame['vza_'+name]=angles[:,i].astype('float32')
            table=pa.Table.from_pandas(frame,preserve_index=False)
            if writer is None: writer=pq.ParquetWriter(tmp,table.schema,compression='zstd')
            writer.write_table(table); total+=len(frame)
            for name,n in frame.geo_platform.fillna('No valid view').value_counts().items(): counts[name]=counts.get(name,0)+int(n)
        writer.close(); writer=None; tmp.replace(path)
    finally:
        if writer is not None: writer.close()
    return dict(n_cells=total,assignment_counts=counts,grid_cell_deg=deg,path=str(path))


def regional_summary(cfg):
    rows=[]; deg=cfg['grid']['cell_deg']
    for name,(w,s,e,n) in cfg['himawari']['regions'].items():
        lon,lat=np.meshgrid(np.arange(w+deg/2,e,deg),np.arange(s+deg/2,n,deg))
        chosen,vza,angles=assign(lon,lat,cfg)
        counts=pd.Series(chosen.ravel()).fillna('No valid view').value_counts().to_dict()
        rows.append(dict(region=name,n_cells=chosen.size,assignment_counts={str(k):int(v) for k,v in counts.items()},
                         mean_selected_vza_deg=float(np.nanmean(vza)),
                         platform_mean_vza_deg={p:float(np.nanmean(angles[...,i])) for i,p in enumerate(cfg['geostationary']['platforms'])}))
    return rows
