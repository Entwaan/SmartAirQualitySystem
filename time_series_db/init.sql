DROP DATABASE IF EXISTS timeseries_db;
CREATE DATABASE timeseries_db;
USE timeseries_db;

CREATE TABLE IF NOT EXISTS air_quality_index (
    id INT PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    building VARCHAR(50),
    floor INT,
    room VARCHAR(50),
    value FLOAT
);
CREATE TABLE IF NOT EXISTS windows (
    id INT PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    building VARCHAR(50),
    floor INT,
    room VARCHAR(50),
    value VARCHAR(50)
);
CREATE TABLE IF NOT EXISTS ventilation (
    id INT PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    building VARCHAR(50),
    floor INT,
    room VARCHAR(50),
    value VARCHAR(50)
);