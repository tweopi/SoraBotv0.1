#!/bin/bash

# Установка системных зависимостей
apt-get update
apt-get install -y build-essential python3-dev

# Установка Python-зависимостей
pip install --no-cache-dir -r requirements.txt