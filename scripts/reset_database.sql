-- Полный сброс только базы newsystem (выполнять от суперпользователя postgres или владельца БД)
-- psql -U postgres -f scripts/reset_database.sql

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'newsystem' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS newsystem;
CREATE DATABASE newsystem ENCODING 'UTF8' TEMPLATE template0;
