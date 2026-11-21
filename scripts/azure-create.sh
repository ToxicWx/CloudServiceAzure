#!/usr/bin/env bash
# Створює всю інфраструктуру CloudDrop в Azure однією командою.
# Запускати в Azure Cloud Shell (Bash): https://shell.azure.com
#
#   bash azure-create.sh                       # з налаштуваннями за замовчуванням
#   EMAIL=you@example.com bash azure-create.sh # + алерт на пошту при CPU > 80%
#   LOCATION=polandcentral bash azure-create.sh

set -euo pipefail

RG="${RG:-rg-clouddrop}"
LOCATION="${LOCATION:-westeurope}"
VM_NAME="${VM_NAME:-vm-clouddrop}"
VM_SIZE="${VM_SIZE:-Standard_B1s}"
ADMIN_USER="${ADMIN_USER:-azureuser}"
STORAGE="${STORAGE:-clouddrop$RANDOM$RANDOM}"   # ім'я має бути унікальним у всьому Azure
EMAIL="${EMAIL:-}"

echo "==> 1/6 Ресурсна група $RG у регіоні $LOCATION"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> 2/6 Віртуальна мережа і підмережа"
az network vnet create -g "$RG" -n vnet-clouddrop \
  --address-prefix 10.0.0.0/16 \
  --subnet-name snet-web --subnet-prefix 10.0.1.0/24 -o none

echo "==> 3/6 Група безпеки мережі (NSG): відкриваємо HTTP (80) і SSH (22)"
az network nsg create -g "$RG" -n nsg-clouddrop -o none
az network nsg rule create -g "$RG" --nsg-name nsg-clouddrop -n allow-http \
  --priority 100 --direction Inbound --access Allow --protocol Tcp \
  --destination-port-ranges 80 -o none
az network nsg rule create -g "$RG" --nsg-name nsg-clouddrop -n allow-ssh \
  --priority 110 --direction Inbound --access Allow --protocol Tcp \
  --destination-port-ranges 22 -o none
az network vnet subnet update -g "$RG" --vnet-name vnet-clouddrop -n snet-web \
  --network-security-group nsg-clouddrop -o none

echo "==> 4/6 Віртуальна машина Linux (Ubuntu 24.04, $VM_SIZE). Це займе 1-2 хв..."
az vm create -g "$RG" -n "$VM_NAME" \
  --image Ubuntu2404 --size "$VM_SIZE" \
  --vnet-name vnet-clouddrop --subnet snet-web --nsg "" \
  --public-ip-sku Standard \
  --admin-username "$ADMIN_USER" --generate-ssh-keys \
  --authentication-type ssh -o none
VM_IP=$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)

echo "==> 5/6 Сховище Azure Storage: $STORAGE"
az storage account create -g "$RG" -n "$STORAGE" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false -o none
CONN=$(az storage account show-connection-string -g "$RG" -n "$STORAGE" -o tsv)

echo "==> 6/6 Моніторинг"
if [[ -n "$EMAIL" ]]; then
  az monitor action-group create -g "$RG" -n ag-clouddrop --short-name clouddrop \
    --action email admin "$EMAIL" -o none
  VM_ID=$(az vm show -g "$RG" -n "$VM_NAME" --query id -o tsv)
  az monitor metrics alert create -g "$RG" -n alert-high-cpu \
    --scopes "$VM_ID" --condition "avg Percentage CPU > 80" \
    --window-size 5m --evaluation-frequency 1m \
    --action ag-clouddrop --description "CPU VM CloudDrop > 80%" -o none
  echo "    Алерт створено: лист на $EMAIL, якщо CPU > 80%"
else
  echo "    Пропущено (щоб створити алерт, запустіть з EMAIL=ваша@пошта)"
fi

cat <<EOF

================== ГОТОВО ==================
Публічна IP-адреса VM:  $VM_IP
Підключення по SSH:     ssh $ADMIN_USER@$VM_IP

Рядок підключення до сховища (вставте у .env на сервері):
AZURE_STORAGE_CONNECTION_STRING=$CONN

Приватний SSH-ключ (знадобиться для GitHub Actions):
  cat ~/.ssh/id_rsa
============================================
EOF
