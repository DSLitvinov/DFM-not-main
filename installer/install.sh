#!/bin/bash
# install.sh - Универсальный установщик Forester для Linux/macOS
# Для Windows используйте install.bat

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Определение ОС
detect_os() {
    case "$(uname -s)" in
        Linux*)
            echo "linux"
            ;;
        Darwin*)
            echo "macos"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Определение архитектуры
detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)
            echo "x64"
            ;;
        arm64|aarch64)
            echo "arm64"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

OS=$(detect_os)
ARCH=$(detect_arch)

echo "=========================================="
echo "  Forester Installer"
echo "=========================================="
echo ""
echo "Обнаружена ОС: ${OS} (${ARCH})"
echo ""

# Проверка наличия бинарника для текущей ОС
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINARY_DIR="${INSTALLER_DIR}/forester/${OS}/bin"

if [ ! -d "${BINARY_DIR}" ]; then
    echo -e "${RED}✗ Ошибка: бинарники для ${OS} не найдены!${NC}"
    echo "Проверьте наличие папки: ${BINARY_DIR}"
    exit 1
fi

BINARY_NAME="forester"
BINARY_PATH="${BINARY_DIR}/${BINARY_NAME}"

if [ ! -f "${BINARY_PATH}" ]; then
    echo -e "${RED}✗ Ошибка: бинарник не найден: ${BINARY_PATH}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Бинарник найден: ${BINARY_PATH}${NC}"
echo ""

# Выбор пути установки
if [ "${OS}" = "linux" ]; then
    DEFAULT_INSTALL_PATH="/opt/Forester"
elif [ "${OS}" = "macos" ]; then
    DEFAULT_INSTALL_PATH="/Applications/Forester"
else
    DEFAULT_INSTALL_PATH="${HOME}/Forester"
fi

read -p "Путь установки [${DEFAULT_INSTALL_PATH}]: " INSTALL_PATH
INSTALL_PATH=${INSTALL_PATH:-${DEFAULT_INSTALL_PATH}}

echo ""
echo "Установка в: ${INSTALL_PATH}"
echo ""

# Создание директории установки
echo "=== Создание директорий ==="
if [ "${OS}" = "linux" ] || [ "${OS}" = "macos" ]; then
    # Для системных директорий может потребоваться sudo
    if [[ "${INSTALL_PATH}" =~ ^/(opt|usr|Applications) ]]; then
        echo -e "${YELLOW}Требуются права администратора для установки в системную директорию${NC}"
        sudo mkdir -p "${INSTALL_PATH}/bin"
        sudo cp "${BINARY_PATH}" "${INSTALL_PATH}/bin/${BINARY_NAME}"
        sudo chmod +x "${INSTALL_PATH}/bin/${BINARY_NAME}"
        INSTALL_CMD="sudo"
    else
        mkdir -p "${INSTALL_PATH}/bin"
        cp "${BINARY_PATH}" "${INSTALL_PATH}/bin/${BINARY_NAME}"
        chmod +x "${INSTALL_PATH}/bin/${BINARY_NAME}"
        INSTALL_CMD=""
    fi
else
    mkdir -p "${INSTALL_PATH}/bin"
    cp "${BINARY_PATH}" "${INSTALL_PATH}/bin/${BINARY_NAME}"
    chmod +x "${INSTALL_PATH}/bin/${BINARY_NAME}"
    INSTALL_CMD=""
fi

echo -e "${GREEN}✓ Бинарник установлен: ${INSTALL_PATH}/bin/${BINARY_NAME}${NC}"
echo ""

# Проверка работы бинарника
echo "=== Проверка установки ==="
INSTALLED_BINARY="${INSTALL_PATH}/bin/${BINARY_NAME}"
if [ -x "${INSTALLED_BINARY}" ]; then
    VERSION_OUTPUT=$("${INSTALLED_BINARY}" --version 2>&1 || "${INSTALLED_BINARY}" --help 2>&1 | head -1)
    echo -e "${GREEN}✓ Бинарник работает${NC}"
    if [ -n "${VERSION_OUTPUT}" ]; then
        echo "  Версия: ${VERSION_OUTPUT}"
    fi
else
    echo -e "${YELLOW}⚠ Не удалось проверить работу бинарника${NC}"
fi

echo ""

# Установка аддонов
if [ -d "${INSTALLER_DIR}/addons" ]; then
    echo "=== Установка аддонов ==="
    
    # Blender аддон
    if [ -d "${INSTALLER_DIR}/addons/blender" ]; then
        read -p "Установить аддон для Blender? [Y/n]: " INSTALL_BLENDER
        INSTALL_BLENDER=${INSTALL_BLENDER:-Y}
        
        if [[ "${INSTALL_BLENDER}" =~ ^[Yy]$ ]]; then
            # Определение пути к аддонам Blender
            if [ "${OS}" = "linux" ]; then
                BLENDER_ADDON_PATH="${HOME}/.config/blender"
            elif [ "${OS}" = "macos" ]; then
                BLENDER_ADDON_PATH="${HOME}/Library/Application Support/Blender"
            else
                BLENDER_ADDON_PATH="${HOME}/.config/blender"
            fi
            
            # Поиск версий Blender
            if [ -d "${BLENDER_ADDON_PATH}" ]; then
                BLENDER_VERSIONS=$(find "${BLENDER_ADDON_PATH}" -maxdepth 1 -type d -name "[0-9]*" 2>/dev/null | sort -V -r)
                
                if [ -n "${BLENDER_VERSIONS}" ]; then
                    echo ""
                    echo -e "${BLUE}Найдены версии Blender:${NC}"
                    echo "${BLENDER_VERSIONS}" | sed 's|.*/|  |'
                    echo ""
                    
                    read -p "Установить для всех версий? [Y/n]: " INSTALL_ALL
                    INSTALL_ALL=${INSTALL_ALL:-Y}
                    
                    if [[ "${INSTALL_ALL}" =~ ^[Yy]$ ]]; then
                        for BLENDER_VERSION in ${BLENDER_VERSIONS}; do
                            ADDON_DEST="${BLENDER_VERSION}/extensions/user_default/difference_machine"
                            mkdir -p "${ADDON_DEST}"
                            cp -r "${INSTALLER_DIR}/addons/blender/difference_machine"/* "${ADDON_DEST}/" 2>/dev/null || {
                                echo -e "${YELLOW}⚠ Не удалось установить для $(basename ${BLENDER_VERSION})${NC}"
                                continue
                            }
                            echo -e "${GREEN}✓ Установлен для Blender $(basename ${BLENDER_VERSION})${NC}"
                        done
                    else
                        echo ""
                        read -p "Введите версию Blender (например: 5.0): " BLENDER_VERSION
                        ADDON_DEST="${BLENDER_ADDON_PATH}/${BLENDER_VERSION}/extensions/user_default/difference_machine"
                        if [ -d "${BLENDER_ADDON_PATH}/${BLENDER_VERSION}" ]; then
                            mkdir -p "${ADDON_DEST}"
                            cp -r "${INSTALLER_DIR}/addons/blender/difference_machine"/* "${ADDON_DEST}/"
                            echo -e "${GREEN}✓ Установлен для Blender ${BLENDER_VERSION}${NC}"
                        else
                            echo -e "${RED}✗ Версия Blender ${BLENDER_VERSION} не найдена${NC}"
                        fi
                    fi
                else
                    echo -e "${YELLOW}⚠ Blender не найден в стандартном расположении${NC}"
                    echo ""
                    read -p "Введите путь к папке extensions/user_default Blender: " CUSTOM_BLENDER_PATH
                    if [ -d "${CUSTOM_BLENDER_PATH}" ]; then
                        ADDON_DEST="${CUSTOM_BLENDER_PATH}/difference_machine"
                        mkdir -p "${ADDON_DEST}"
                        cp -r "${INSTALLER_DIR}/addons/blender/difference_machine"/* "${ADDON_DEST}/"
                        echo -e "${GREEN}✓ Установлен в: ${ADDON_DEST}${NC}"
                    else
                        echo -e "${RED}✗ Путь не найден: ${CUSTOM_BLENDER_PATH}${NC}"
                    fi
                fi
            else
                echo -e "${YELLOW}⚠ Blender не найден в стандартном расположении${NC}"
                echo ""
                read -p "Введите путь к папке extensions/user_default Blender: " CUSTOM_BLENDER_PATH
                if [ -d "${CUSTOM_BLENDER_PATH}" ]; then
                    ADDON_DEST="${CUSTOM_BLENDER_PATH}/difference_machine"
                    mkdir -p "${ADDON_DEST}"
                    cp -r "${INSTALLER_DIR}/addons/blender/difference_machine"/* "${ADDON_DEST}/"
                    echo -e "${GREEN}✓ Установлен в: ${ADDON_DEST}${NC}"
                else
                    echo -e "${RED}✗ Путь не найден: ${CUSTOM_BLENDER_PATH}${NC}"
                fi
            fi
        fi
    fi
    
    # Здесь можно добавить установку других аддонов (Maya, C4D)
fi

# Создание конфигурационного файла
echo ""
echo "=== Создание конфигурационного файла ==="
DFM_SETUP_DIR="${HOME}/.dfm-setup"
DFM_CONFIG_FILE="${DFM_SETUP_DIR}/setup.cfg"

mkdir -p "${DFM_SETUP_DIR}"

cat > "${DFM_CONFIG_FILE}" << EOF
[forester]
path = ${INSTALL_PATH}
EOF

if [ -f "${DFM_CONFIG_FILE}" ]; then
    echo -e "${GREEN}✓ Конфигурационный файл создан: ${DFM_CONFIG_FILE}${NC}"
else
    echo -e "${YELLOW}⚠ Не удалось создать конфигурационный файл${NC}"
    echo "Создайте вручную: ${DFM_CONFIG_FILE}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Установка завершена!${NC}"
echo "=========================================="
echo ""
echo "Forester CLI установлен в: ${INSTALL_PATH}/bin/${BINARY_NAME}"
echo "Конфигурация аддона: ${DFM_CONFIG_FILE}"
echo ""
echo "Добавьте в PATH для удобства:"
echo "  export PATH=\"${INSTALL_PATH}/bin:\$PATH\""
echo ""
echo "Или создайте симлинк:"
if [ "${OS}" = "linux" ]; then
    echo "  sudo ln -s ${INSTALL_PATH}/bin/${BINARY_NAME} /usr/local/bin/forester"
elif [ "${OS}" = "macos" ]; then
    echo "  sudo ln -s ${INSTALL_PATH}/bin/${BINARY_NAME} /usr/local/bin/forester"
fi
echo ""
