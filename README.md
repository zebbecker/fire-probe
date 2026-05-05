# fire-probe

Quick black-box data freshness checker for the [FEDS NRT API](https://earth-information-system.github.io/fireatlas/docs/nrt.html). Writes to `data/probe-results.csv`. Currently, checks the following collections: 
- public.eis_fire_lf_perimeter_nrt
- public.eis_fire_lf_newfirepix_nrt
- public.eis_fire_fireline_nrt

Uses pixi for cross-platform environment reproducibility. Install instructions [here](https://pixi.prefix.dev/latest/installation/) if needed. 



### Setup/actions: 
```
git clone https://github.com/zebbecker/fire-probe.git; cd fire-probe

# check and record latest timestep available on API
pixi run probe

# run tests
pixi run pytest

# run linter
pixi run lint

# autoformat code
pixi run format

```

For scheduled runs: 

`crontab -e; */10 * * * * /home/zeb/fire-probe/probe.sh >> /home/zeb/fire-probe/probe.log 2>&1`

To setup for analysis with the optional deps, use the dev environment. 

```
pixi install -e dev 
pixi run -e python {whatever}
```

To use with a jupyter notebook, register the kernel with the dev environment: 

```
pixi run -e dev python -m ipykernel install --user --name fire-probe-dev --display-name "fire-probe-dev (pixi)"
```

