#!/usr/bin/env bash
# Налаштування сервера: встановлює Docker і готує папку проєкту.
# Запускати на VM після підключення по SSH:
#   bash setup-vm.sh

set -euo pipefail

echo "==> Оновлення системи"
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> Встановлення Docker (офіційний скрипт)"
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"

echo "==> Брандмауер ufw (додатковий захист, крім NSG в Azure)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw --force enable

echo "==> Папка проєкту"
mkdir -p ~/clouddrop

echo
echo "Готово! Вийдіть (exit) і зайдіть по SSH знову, щоб діяли права на Docker."
echo "Далі створіть файл ~/clouddrop/.env (див. README, крок 5)."
