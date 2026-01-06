#!/bin/bash
# build_installer.sh - Сборка установщика для всех платформ
# Копирует бинарники из installer/forester/ в installer/DFM_Installer/forester/
# Копирует аддоны из addons/ в installer/DFM_Installer/addons/
# Копирует скрипты установки в installer/DFM_Installer/

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALLER_DIR="${SCRIPT_DIR}"
DFM_INSTALLER_DIR="${INSTALLER_DIR}/DFM_Installer"

echo "=========================================="
echo "  Сборка установщика Forester"
echo "=========================================="
echo ""
echo "Корень проекта: ${PROJECT_ROOT}"
echo "Директория установщика: ${INSTALLER_DIR}"
echo "Целевая директория: ${DFM_INSTALLER_DIR}"
echo ""

# Очистка целевой директории (опционально, можно закомментировать)
if [ -d "${DFM_INSTALLER_DIR}" ]; then
    echo "=== Очистка целевой директории ==="
    rm -rf "${DFM_INSTALLER_DIR}"
    echo -e "${GREEN}✓ Старая директория очищена${NC}"
    echo ""
fi

# Создание структуры
echo "=== Создание структуры директорий ==="
mkdir -p "${DFM_INSTALLER_DIR}"
echo -e "${GREEN}✓ Структура создана${NC}"
echo ""

# Копирование бинарников из installer/forester/
echo "=== Копирование бинарников ==="
FORESTER_SOURCE_DIR="${INSTALLER_DIR}/forester"

if [ -d "${FORESTER_SOURCE_DIR}" ]; then
    echo "Копирование бинарников из ${FORESTER_SOURCE_DIR}..."
    cp -r "${FORESTER_SOURCE_DIR}" "${DFM_INSTALLER_DIR}/"
    
    # Установка прав на выполнение для бинарников
    if [ -f "${DFM_INSTALLER_DIR}/forester/linux/bin/forester" ]; then
        chmod +x "${DFM_INSTALLER_DIR}/forester/linux/bin/forester"
        echo -e "${GREEN}✓ Linux бинарник скопирован${NC}"
    fi
    if [ -f "${DFM_INSTALLER_DIR}/forester/macos/bin/forester" ]; then
        chmod +x "${DFM_INSTALLER_DIR}/forester/macos/bin/forester"
        echo -e "${GREEN}✓ macOS бинарник скопирован${NC}"
    fi
    if [ -f "${DFM_INSTALLER_DIR}/forester/windows/bin/forester.exe" ]; then
        echo -e "${GREEN}✓ Windows бинарник скопирован${NC}"
    fi
    echo -e "${GREEN}✓ Бинарники скопированы${NC}"
else
    echo -e "${YELLOW}⚠ Папка installer/forester/ не найдена${NC}"
    echo "  Поместите бинарники в installer/forester/{linux,macos,windows}/bin/"
fi
echo ""

# Копирование аддонов
echo "=== Копирование аддонов ==="
if [ -d "${PROJECT_ROOT}/addons" ]; then
    echo "Копирование аддонов из ${PROJECT_ROOT}/addons..."
    cp -r "${PROJECT_ROOT}/addons" "${DFM_INSTALLER_DIR}/"
    echo -e "${GREEN}✓ Аддоны скопированы${NC}"
else
    echo -e "${YELLOW}⚠ Папка addons/ не найдена${NC}"
fi
echo ""

# Копирование скриптов установки
echo "=== Копирование скриптов установки ==="
if [ -f "${INSTALLER_DIR}/install.sh" ]; then
    cp "${INSTALLER_DIR}/install.sh" "${DFM_INSTALLER_DIR}/"
    chmod +x "${DFM_INSTALLER_DIR}/install.sh"
    echo -e "${GREEN}✓ install.sh скопирован${NC}"
else
    echo -e "${YELLOW}⚠ install.sh не найден в installer/${NC}"
fi

if [ -f "${INSTALLER_DIR}/install.bat" ]; then
    cp "${INSTALLER_DIR}/install.bat" "${DFM_INSTALLER_DIR}/"
    echo -e "${GREEN}✓ install.bat скопирован${NC}"
else
    echo -e "${YELLOW}⚠ install.bat не найден в installer/${NC}"
fi
echo ""

# Создание README для установщика
echo "=== Создание README ==="
cat > "${DFM_INSTALLER_DIR}/README.txt" << 'EOF'
Forester Installer
==================

Этот установщик содержит:
- Бинарники Forester CLI для разных операционных систем
- Аддоны для различных редакторов (Blender, и др.)
- Скрипты установки

БЫСТРЫЙ СТАРТ:
--------------

Linux/macOS:
  ./install.sh

Windows:
  install.bat

ПОДРОБНЫЕ ИНСТРУКЦИИ:
---------------------

См. файлы:
- README.md - Полная документация (на английском)
- INSTALLATION_GUIDE_RU.md - Руководство по установке (на русском)

СТРУКТУРА:
----------
DFM_Installer/
├── forester/
│   ├── linux/bin/forester      - Бинарник для Linux
│   ├── windows/bin/forester.exe - Бинарник для Windows
│   └── macos/bin/forester      - Бинарник для macOS
├── addons/                      - Аддоны для редакторов
├── install.sh                   - Скрипт установки (Linux/macOS)
└── install.bat                  - Скрипт установки (Windows)
EOF

echo -e "${GREEN}✓ README.txt создан${NC}"
echo ""

# Создание ISO-образа
echo "=== Создание ISO-образа ==="
ISO_FILENAME="DFM_Installer.iso"
ISO_PATH="${INSTALLER_DIR}/${ISO_FILENAME}"

# Удаление старого ISO, если существует
if [ -f "${ISO_PATH}" ]; then
    rm -f "${ISO_PATH}"
    echo "Старый ISO-файл удален"
fi

# Определение доступного инструмента для создания ISO
ISO_TOOL=""
if command -v genisoimage >/dev/null 2>&1; then
    ISO_TOOL="genisoimage"
elif command -v mkisofs >/dev/null 2>&1; then
    ISO_TOOL="mkisofs"
elif command -v xorriso >/dev/null 2>&1; then
    ISO_TOOL="xorriso"
fi

if [ -n "${ISO_TOOL}" ]; then
    echo "Используется инструмент: ${ISO_TOOL}"
    
    case "${ISO_TOOL}" in
        genisoimage|mkisofs)
            "${ISO_TOOL}" -o "${ISO_PATH}" \
                -V "DFM_Installer" \
                -J -r \
                "${DFM_INSTALLER_DIR}"
            ;;
        xorriso)
            xorriso -outdev "${ISO_PATH}" \
                -volid "DFM_Installer" \
                -map "${DFM_INSTALLER_DIR}" "/" \
                -chmod 0755 -- \
                -commit
            ;;
    esac
    
    if [ -f "${ISO_PATH}" ]; then
        ISO_SIZE=$(du -h "${ISO_PATH}" | cut -f1)
        echo -e "${GREEN}✓ ISO-образ создан: ${ISO_FILENAME} (${ISO_SIZE})${NC}"
        
        # Удаление временной директории после успешного создания ISO
        echo "=== Удаление временной директории ==="
        rm -rf "${DFM_INSTALLER_DIR}"
        echo -e "${GREEN}✓ Временная директория ${DFM_INSTALLER_DIR} удалена${NC}"
    else
        echo -e "${RED}✗ Ошибка при создании ISO-образа${NC}"
        echo -e "${YELLOW}⚠ Временная директория ${DFM_INSTALLER_DIR} сохранена для отладки${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ Инструмент для создания ISO не найден${NC}"
    echo "  Установите один из: genisoimage, mkisofs или xorriso"
    echo "  Ubuntu/Debian: sudo apt-get install genisoimage"
    echo "  Fedora/RHEL: sudo dnf install genisoimage"
    echo "  macOS: brew install cdrtools"
    echo ""
    echo -e "${YELLOW}⚠ ISO-образ не создан, структура установщика сохранена в ${DFM_INSTALLER_DIR}${NC}"
fi
echo ""

echo "=========================================="
if [ -f "${ISO_PATH}" ]; then
    echo -e "${GREEN}✓ ISO-образ установщика готов!${NC}"
    echo "=========================================="
    echo ""
    echo "ISO-образ: ${ISO_PATH}"
    echo ""
    echo "Следующие шаги:"
    echo "1. ISO-образ готов к распространению"
    echo "2. Монтируйте ISO и запустите установку:"
    echo "   Linux: sudo mount -o loop ${ISO_FILENAME} /mnt"
    echo "   macOS: hdiutil attach ${ISO_FILENAME}"
    echo "   Windows: смонтируйте ISO через Проводник"
    echo ""
else
    echo -e "${YELLOW}⚠ Структура установщика готова, но ISO не создан${NC}"
    echo "=========================================="
    echo ""
    echo "Временная директория: ${DFM_INSTALLER_DIR}"
    echo ""
    echo "Следующие шаги:"
    echo "1. Убедитесь, что бинарники помещены в installer/forester/{linux,macos,windows}/bin/"
    echo "2. Установите инструмент для создания ISO:"
    echo "   Ubuntu/Debian: sudo apt-get install genisoimage"
    echo "   Fedora/RHEL: sudo dnf install genisoimage"
    echo "   macOS: brew install cdrtools"
    echo "3. Перезапустите этот скрипт для создания ISO"
    echo ""
    echo "Для тестирования установки (из директории):"
    echo "  cd installer/DFM_Installer"
    echo "  ./install.sh  # Linux/macOS"
    echo "  install.bat   # Windows"
    echo ""
fi
