FROM mysql:8

ENV MYSQL_ROOT_PASSWORD=root
ENV MYSQL_DATABASE=timeseries_db
ENV MYSQL_USER=admin
ENV MYSQL_PASSWORD=admin

# SQL file to create the tables
COPY init.sql /docker-entrypoint-initdb.d/
