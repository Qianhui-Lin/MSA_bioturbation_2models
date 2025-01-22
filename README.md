### Start Each Microservice Individually
python microservice/model/model_1.py
python microservice/model/model_2.py
python microservice/plotting/plotting.py

### Pass data to orchestrator
python orchestrator/bioturbation_orchestrator.py client/config.json



### Initialize database

python database/database_initialize.py

### Data structure
[
  {
    _id: ObjectId('678fccac3fa7016626fa55f6'),
    model: 'Model1',
    layers: [
      {
        id: 1,depth: 0.1,conc: 4e-9,earthworm_density: 20,beta: 1e-8, bioturbation_rate: 0.000002
      },
      {
        id: 2,depth: 0.1,conc: 0,earthworm_density: 20,beta: 1e-8,bioturbation_rate: 0.000002
      },
      {
        id: 3,depth: 0.1,conc: 0,earthworm_density: 20,beta: 1e-8,
        bioturbation_rate: 0.000002
      },
      {
        id: 4,depth: 0.1,conc: 0,earthworm_density: 20,beta: 1e-8,
        bioturbation_rate: 0.000002
      }
    ],
    steady_state_tol: 1e-12,
    dt: 86400,
    max_iter: 10000,
    profile: { id: 1 }
  }
]
