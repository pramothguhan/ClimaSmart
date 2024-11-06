import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from google.cloud import storage
import io
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BUCKET_NAME = 'us-east1-climasmart-fefe9cc2-bucket'

def load_data_from_gcs(bucket_name, file_name):
    """Load CSV data from Google Cloud Storage into a DataFrame."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    data = blob.download_as_string()
    df = pd.read_csv(io.BytesIO(data))
    logging.info(f"Loaded {file_name} from GCS.")
    return df

def save_data_to_gcs(df, bucket_name, file_name):
    """Save DataFrame as a CSV file in Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    blob.upload_from_file(output, content_type='text/csv')
    logging.info(f"Saved {file_name} to GCS.")

def save_plot_to_gcs(bucket_name, plot_name):
    """Save the current matplotlib plot to Google Cloud Storage in a specific folder."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"weather_data_plots/{plot_name}.png")
    plot_image = io.BytesIO()
    plt.savefig(plot_image, format='png')
    plot_image.seek(0)
    blob.upload_from_file(plot_image, content_type='image/png')
    logging.info(f"Plot {plot_name} saved to GCS in folder weather_data_plots.")

def eda_and_visualizations(hourly_data, daily_data):
    logging.info("Starting EDA and visualizations.")
    
    # Correlation heatmap for hourly data (numeric columns only)
    plt.figure(figsize=(20, 16))
    sns.heatmap(hourly_data.select_dtypes(include=[np.number]).corr(), annot=False, cmap='coolwarm')
    plt.title('Correlation Heatmap - Hourly Data')
    save_plot_to_gcs(BUCKET_NAME, 'correlation_heatmap_hourly')
    plt.clf()

    # Correlation heatmap for daily data (numeric columns only)
    plt.figure(figsize=(20, 16))
    sns.heatmap(daily_data.select_dtypes(include=[np.number]).corr(), annot=False, cmap='coolwarm')
    plt.title('Correlation Heatmap - Daily Data')
    save_plot_to_gcs(BUCKET_NAME, 'correlation_heatmap_daily')
    plt.clf()

    # Time series plot of temperature and precipitation (hourly data)
    plt.figure(figsize=(20, 10))
    plt.plot(hourly_data['datetime'], hourly_data['temperature_2m'], label='Temperature')
    plt.plot(hourly_data['datetime'], hourly_data['precipitation'], label='Precipitation')
    plt.title('Temperature and Precipitation Over Time')
    plt.xlabel('Date')
    plt.ylabel('Value')
    plt.legend()
    save_plot_to_gcs(BUCKET_NAME, 'time_series_temp_precip')
    plt.clf()

    # Distribution of temperature (daily data)
    plt.figure(figsize=(12, 6))
    sns.histplot(data=daily_data, x='temperature_2m_max', kde=True)
    plt.title('Distribution of Daily Maximum Temperature')
    save_plot_to_gcs(BUCKET_NAME, 'distribution_daily_max_temp')
    plt.clf()

    # Box plot of precipitation by season (daily data)
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=daily_data, x='season', y='precipitation_sum')
    plt.title('Precipitation by Season')
    save_plot_to_gcs(BUCKET_NAME, 'boxplot_precip_by_season')
    plt.clf()
    
    logging.info("EDA and visualizations completed.")

def engineer_hourly_features(df):
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Factorize the season column
    df['season'] = pd.factorize(df['season'])[0]
    
    # Extract more time-based features
    df['month'] = df['datetime'].dt.month
    df['day_of_week'] = df['datetime'].dt.dayofweek
    df['is_holiday'] = ((df['is_weekend'] == 1) | (df['datetime'].dt.month == 12) & (df['datetime'].dt.day == 25)).astype(int)

    # Calculate rolling averages for temperature and precipitation
    df['temp_rolling_mean_24h'] = df['temperature_2m'].rolling(window=24).mean()
    df['precip_rolling_sum_24h'] = df['precipitation'].rolling(window=24).sum()

    # Create binary features for extreme weather conditions
    df['is_freezing'] = (df['temperature_2m'] <= 0).astype(int)
    df['is_raining'] = (df['precipitation'] > 0).astype(int)
    df['is_snowing'] = (df['snowfall'] > 0).astype(int)

    # Calculate wind chill factor
    df['wind_chill'] = 13.12 + 0.6215 * df['temperature_2m'] - 11.37 * (df['wind_speed_10m'] * 3.6)**0.16 + 0.3965 * df['temperature_2m'] * (df['wind_speed_10m'] * 3.6)**0.16

    # Calculate heat index
    df['heat_index'] = -42.379 + 2.04901523 * df['temperature_2m'] + 10.14333127 * df['relative_humidity_2m'] - 0.22475541 * df['temperature_2m'] * df['relative_humidity_2m'] - 6.83783e-3 * df['temperature_2m']**2 - 5.481717e-2 * df['relative_humidity_2m']**2 + 1.22874e-3 * df['temperature_2m']**2 * df['relative_humidity_2m'] + 8.5282e-4 * df['temperature_2m'] * df['relative_humidity_2m']**2 - 1.99e-6 * df['temperature_2m']**2 * df['relative_humidity_2m']**2

    # Calculate dew point depression
    df['dew_point_depression'] = df['temperature_2m'] - df['dew_point_2m']

    # Calculate relative humidity from dew point
    df['calculated_relative_humidity'] = 100 * (np.exp((17.625 * df['dew_point_2m']) / (243.04 + df['dew_point_2m'])) / np.exp((17.625 * df['temperature_2m']) / (243.04 + df['temperature_2m'])))

    # Create wind speed categories
    df['wind_category'] = pd.cut(df['wind_speed_10m'], bins=[0, 2, 5, 8, 11, np.inf], labels=['Calm', 'Light', 'Moderate', 'Fresh', 'Strong'])

    return df

def engineer_daily_features(df):
    df['date'] = pd.to_datetime(df['date'])
    
    # Factorize the season column
    df['season'] = pd.factorize(df['season'])[0]
    
    # Drop specified columns
    df.drop(columns=['wind_speed_10m_max', 'wind_gusts_10m_max', 'wind_direction_10m_dominant', 'shortwave_radiation_sum', 'et0_fao_evapotranspiration'], inplace=True)
    
    # Calculate temperature range
    df['temperature_range'] = df['temperature_2m_max'] - df['temperature_2m_min']

    # Create binary features for extreme weather conditions
    df['is_hot_day'] = (df['temperature_2m_max'] > df['temperature_2m_max'].quantile(0.9)).astype(int)
    df['is_cold_day'] = (df['temperature_2m_min'] < df['temperature_2m_min'].quantile(0.1)).astype(int)
    df['is_rainy_day'] = (df['precipitation_sum'] > 0).astype(int)

    # Calculate precipitation intensity
    df['precipitation_intensity'] = df['precipitation_sum'] / df['precipitation_hours'].replace(0, np.nan)

    # Calculate diurnal temperature range
    df['diurnal_temp_range'] = df['temperature_2m_max'] - df['temperature_2m_min']

    # Calculate sunshine ratio
    df['sunshine_ratio'] = df['sunshine_duration'] / df['daylight_duration']

    # Calculate rain to total precipitation ratio
    df['rain_ratio'] = df['rain_sum'] / df['precipitation_sum'].replace(0, np.nan)

    # Create a feature for extreme precipitation
    df['is_heavy_precipitation'] = (df['precipitation_sum'] > df['precipitation_sum'].quantile(0.95)).astype(int)

    return df

def feature_engineering():
    logging.info("Starting feature engineering task.")
    
    # Load preprocessed data from GCS
    hourly_data = load_data_from_gcs(BUCKET_NAME, 'weather_data/preprocessed_hourly_data.csv')
    daily_data = load_data_from_gcs(BUCKET_NAME, 'weather_data/preprocessed_daily_data.csv')
    
    # Apply feature engineering transformations
    hourly_data = engineer_hourly_features(hourly_data)
    daily_data = engineer_daily_features(daily_data)
    
    # Save the engineered data back to GCS
    save_data_to_gcs(hourly_data, BUCKET_NAME, 'weather_data/engineered_hourly_data.csv')
    save_data_to_gcs(daily_data, BUCKET_NAME, 'weather_data/engineered_daily_data.csv')
    
    # Perform EDA and visualizations, saving each plot to GCS
    eda_and_visualizations(hourly_data, daily_data)
    
    logging.info("Feature engineering and EDA task completed.")