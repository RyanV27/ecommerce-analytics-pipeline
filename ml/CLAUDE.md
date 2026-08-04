## ML conventions

- Always pull features from the Gold layer (`gold.*` tables), never from Bronze/Silver directly
- Log every training run to MLflow: params, metrics (at minimum AUC for classification, MAPE for forecasting), and the serialized model artifact
- Repeat-purchase propensity model target AUC: > 0.70
- K-means segmentation: 5 clusters, log silhouette score to MLflow
- Prophet models: weekly + yearly seasonality; skip categories with fewer than 10 data points
