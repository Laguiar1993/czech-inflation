"""Offline source audit and exactly84 missing-only import history extensions.

No estimator, outcome access, network or original-file mutation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/research_r14b/imports'
SOURCES={
    'CEN0303.csv':'https://data.csu.gov.cz/opendata/sady/CEN0303/distribuce/csv',
    'CEN0301.csv':'https://data.csu.gov.cz/opendata/sady/CEN0301/distribuce/csv',
    'CEN0303_catalog.json':'https://data.csu.gov.cz/api/katalog/v1/sady/CEN0303/vybery',
    'methodology.html':'https://csu.gov.cz/indexy_cen_dovozu_a_vyvozu',
    'statistical_methodology.html':'https://csu.gov.cz/metodika-statistiky-za-oblast-indexy-cen-vyvozu-a-dovozu',
    'standard_revision_2024.pdf':'https://csu.gov.cz/docs/107516/cb4c358c-276c-6fef-997d-246c47e2a14d/standardni_revize_indexu_vyvoznich_a_dovoznich_cen.pdf?version=1.2',
    'latest_release.html':'https://csu.gov.cz/ceny-vyvozu-a-dovozu',
    'release_2008_01.html':'https://csu.gov.cz/rychle-informace/indexy-cen-vyvozu-a-dovozu-leden-2008-ac9y0iu5ch',
    'release_2014_01.html':'https://csu.gov.cz/rychle-informace/indexy-cen-vyvozu-a-dovozu-leden-2014-1xh613weya',
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_clock(month):
    return (pd.Period(month,'M')+3).to_timestamp().tz_localize('Europe/Prague')


def extract(frame,classification):
    total=(frame.SITCVAD.eq('00890001') if classification=='SITC'
           else frame['Klasifikace CZ-CPA-Úhrn a sekce'].eq('Úhrn celkem'))
    mask=(frame.IndicatorType.eq('614703') & frame.TYPUDAJE5B.eq('IM')
          & frame.Uz0.eq('CZ') & total & frame.CASMKMQRM12.str.fullmatch(r'\d{4}-\d{2}'))
    chosen=frame.loc[mask,['CASMKMQRM12','Hodnota']].copy()
    assert not chosen.CASMKMQRM12.duplicated().any(), 'duplicate source month'
    assert len(chosen)>0, 'empty total selector'
    result=pd.Series(chosen.Hodnota.astype(float).to_numpy()-100,
                     index=pd.PeriodIndex(chosen.CASMKMQRM12,freq='M'),name='value').sort_index()
    assert np.isfinite(result).all() and (result>-100).all()
    assert result.index.equals(pd.period_range(result.index[0],result.index[-1],freq='M'))
    return result


def extend_features(original,prices):
    """Keep existing field strings, including numerical precision, untouched."""
    result=original.copy(deep=True)
    for i,row in original.iterrows():
        source=pd.Period(row.period,'M')-2
        if row.import_l2=='' and pd.Period('2008-01')<=source<pd.Period('2015-01') and source in prices.index:
            result.loc[i,'import_l2']=str(float(prices.loc[source]))
    return result


def run(destination=DATA):
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    sitc=extract(pd.read_csv(DATA/'raw/CEN0303.csv',dtype=str),'SITC')
    cpa=extract(pd.read_csv(DATA/'raw/CEN0301.csv',dtype=str),'CPA')
    assert len(sitc)==222 and str(sitc.index[0])=='2008-01' and str(sitc.index[-1])=='2026-06'
    prior=pd.read_csv(ROOT/'data/czso_import_prices_sitc_monthly.csv',float_precision='round_trip')
    prior=pd.Series(prior.value.to_numpy(),index=pd.PeriodIndex(prior.month,freq='M'),name='prior_cache')
    original=pd.read_csv(ROOT/'tests/fixtures/cleanup/core_features.csv',dtype=str,keep_default_na=False)
    finite=pd.to_numeric(original.import_l2,errors='coerce').notna()
    core=pd.Series(pd.to_numeric(original.loc[finite,'import_l2']).to_numpy(),
        index=pd.PeriodIndex(original.loc[finite,'period'],freq='M')-2,name='frozen_core')
    comparison=pd.concat([sitc.rename('official_sitc'),cpa.rename('official_cpa'),prior,core],axis=1)
    rows=[]
    for name in ('official_cpa','prior_cache','frozen_core'):
        joined=comparison[['official_sitc',name]].dropna(); diff=joined.official_sitc-joined[name]
        comparison['difference_vs_'+name]=comparison.official_sitc-comparison[name]
        assert np.allclose(diff,0,atol=1e-10,rtol=0), f'concept/value mismatch versus {name}'
        rows.append(dict(reference=name,n=len(joined),first=str(joined.index[0]),last=str(joined.index[-1]),
            max_abs_difference=float(abs(diff).max()),n_exceeding_0_1pp=int((abs(diff)>.100000001).sum())))
    assert int(core.size)==137
    comparison.index.name='source_month'; comparison.to_csv(destination/'overlap_comparison.csv')
    pd.DataFrame(rows).to_csv(destination/'overlap_summary.csv',index=False)
    payload=pd.DataFrame({'source_month':sitc.index.astype(str),'import_mm':sitc.to_numpy(),
        'available_from':[source_clock(m).isoformat() for m in sitc.index],
        'availability_policy':'conservative_source_plus3_month_start_not_observed_release'})
    payload.to_csv(destination/'imports_monthly_verified.csv',index=False)
    extended=extend_features(original,sitc)
    changed=extended.ne(original)
    assert int(changed.sum().sum())==84 and int(changed.import_l2.sum())==84
    assert (original.loc[changed.import_l2,'import_l2']=='').all()
    assert extended.loc[finite].equals(original.loc[finite])
    extended.to_csv(destination/'core_features_extended.csv',index=False)
    affected=extended.loc[changed.import_l2,['period','import_l2']].copy()
    affected['available_from']=[source_clock(pd.Period(m)-2).isoformat() for m in affected.period]
    assert affected.period.tolist()==pd.period_range('2008-03','2015-02',freq='M').astype(str).tolist()
    affected.to_csv(destination/'core_feature_extension.csv',index=False)
    source_files=[DATA/'raw'/name for name in SOURCES]
    dependencies=source_files+[Path(__file__),Path(__file__).with_name('test_prepare.py'),
        ROOT/'docs/implementation/R14B_IMPORT_HISTORY_AUDIT.md',
        ROOT/'data/czso_import_prices_sitc_monthly.csv',ROOT/'tests/fixtures/cleanup/core_features.csv',
        ROOT/'data/local_adapter.py',ROOT/'path_step4_backtest.py',ROOT/'PATH_SPEC_v4.md']
    outputs=['overlap_comparison.csv','overlap_summary.csv','imports_monthly_verified.csv',
             'core_features_extended.csv','core_feature_extension.csv']
    manifest=dict(inputs={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(dependencies)},
        outputs={name:sha(destination/name) for name in outputs},
        sources=[dict(file=p.relative_to(ROOT).as_posix(),url=SOURCES[p.name],sha256=sha(p),bytes=p.stat().st_size,
            retrieved_completed_utc=pd.Timestamp(p.stat().st_mtime,unit='s',tz='UTC').isoformat()) for p in source_files],
        extension=dict(n=84,source_start='2008-01',source_end='2014-12',fixture_start='2008-03',fixture_end='2015-02',
            column='import_l2',available_from='source month+3 start Europe/Prague; conservative reconstructed bound',
            finite_existing_cells_changed=0,other_columns_changed=0,new_rows=0),overlap=rows,
        limitation='Latest-vintage source, not vintage archive; reconstructed availability; historical weighting revisions retained.')
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'extension':manifest['extension'],'overlap':rows},indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.verify:
        expected=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
        for name,value in expected['inputs'].items(): assert sha(ROOT/name)==value, name
        for name,value in expected['outputs'].items(): assert sha(DATA/name)==value, name
        with tempfile.TemporaryDirectory(prefix='r14b_import_verify_') as tmp:
            fresh=run(tmp); assert fresh==expected, 'offline preparation differs'
        print('Verified: five data outputs and manifest reproduce exactly offline.')
    else: run()
