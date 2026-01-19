# Difference Machine 0.3 Ptototype
A hybrid version control system for 3D models and code, integrated with Blender.

## 📋 Description  
**Difference Machine** is a comprehensive solution for managing versions of 3D projects, consisting of:  
- **Forester CLI** – the core version control system written in Go  
- **Difference Machine Addon** – a Blender add-on providing a graphical interface  
- **Python API** – a high-level API for integration with other applications  

## 🏗️ Project Structure  
```
difference-machine/
├── forester/             # Core CLI (Go)
│   ├── cmd/forester/     # CLI entry point
│   ├── internal/         # Internal packages
│   │   ├── commands/    # CLI commands
│   │   ├── core/        # Core components (storage, database, hashing)
│   │   ├── models/      # Data models
│   │   └── utils/        # Utilities
│   ├── go.mod           # Go module
│   ├── Makefile         # Build configuration
│   └── README.md        # Forester CLI documentation
│
├── addons/               # Editor add-ons
│   └── blender/
│       └── difference-machine/  # Blender add-on
│
├── forester_api/         # Python API wrapper
│   └── README.md         # API documentation
│
└── installer/            # Installer
    ├── install.sh        # Linux/macOS installer
    ├── install.bat       # Windows installer
    └── README.md         # Installer documentation
```

## 🚀 Quick Start  

### 1. Install Forester CLI  
**Linux:**  
```bash
cd forester
./LINUX_build_and_install.sh
```

**macOS:**  
```bash
cd forester
./MACOS_build_and_install.sh
```

**Windows:**  
```bat
cd forester
WINDOWS_build_and_install.bat
```

Forester will be installed to:  
- **Linux**: `/opt/Forester/bin/forester`  
- **macOS**: `/Applications/Forester/bin/forester`  
- **Windows**: `C:\Program Files\Forester\bin\forester.exe` or `installer/forester/windows/bin/forester.exe`

### 2. Configure for Blender Add-on  
```bash
mkdir -p ~/.dfm-setup
cat > ~/.dfm-setup/setup.cfg << 'CFG'
[forester]
path = /opt/Forester
CFG
```

### 3. Install the Blender Add-on  
You can install the add-on manually or use the installer:  
```bash
cd installer
./install.sh  # Linux/macOS
# or
install.bat   # Windows
```

### 4. Use in Blender  
1. Open Blender  
2. Go to `Edit` → `Preferences` → `Add-ons`  
3. Search for "Difference Machine"  
4. Enable the add-on  
The add-on will automatically detect the installed Forester CLI.


## 🔧 Components  

### Forester CLI  
The core version control engine written in Go. Provides all fundamental operations:  
- Repository initialization  
- Commit creation  
- Branch management  
- History and diff viewing  
- Tagging system  
- Garbage collection  
- And more  

**Key Features:**  
- Single static binary with no dependencies  
- Easy cross-compilation for all platforms  
- Automatic memory management  
- Built-in concurrency support  
- Object deduplication  
- Support for both 3D models and code  
- Reflog mechanism for safe commit deletion  

### Difference Machine Add-on (Blender)  
A graphical interface for working with Forester inside Blender, offering:  
- Visual UI for all operations  
- Seamless integration into Blender workflows  
- History browsing and version comparison  
- Branch and tag management  
- Review system  

### Python API  
A high-level Python API for integration with external applications:  
- Unified interface (CLI and C++ bindings)  
- Automatic backend detection  
- Type-safe data models  

## 💻 Core CLI Commands  
```bash
# Initialize repository
forester init

# Check status
forester status

# Create a commit
forester commit -m "Commit message"

# Branch management
forester branch feature-name
forester checkout feature-name

# View history
forester log

# View differences
forester diff

# Help
forester --help
```

## 🛠️ Requirements  

### To Build Forester CLI  
- Go 1.21 or higher  
- SQLite3 (library and header files for CGO)  
- C compiler (for CGO; usually bundled with Go or MinGW)  

### For Blender Add-on  
- Blender 4.5.0 or higher  
- Forester CLI (installed and configured)  
- Python 3.10+ (bundled with Blender)  

## 📦 Installation via Installer  
Easy one-step installation for all components:  
```bash
cd installer
./install.sh  # Linux/macOS
# or
install.bat   # Windows
```

The installer will:  
- Install Forester CLI  
- Set up configuration  
- Install the Blender add-on  
- Configure paths  

More details: [installer/README.md](installer/README.md)

## 🔄 Workflow  

### Basic CLI Workflow  
```bash
# 1. Initialize project
forester init

# 2. Check status
forester status

# 3. Create initial commit
forester commit -m "Initial commit"

# 4. Work on a new branch
forester branch feature-new-model
forester checkout feature-new-model

# 5. Commit changes
forester commit -m "Add new model"

# 6. Switch back to main
forester checkout main
```

### In Blender  
- Open the Difference Machine panel  
- Initialize the repository via UI  
- Use buttons to create commits, switch branches, and view history  
- All operations are performed through the graphical interface  

## 🗂️ Repository File Structure  
After initialization, the following structure is created:  
```
project/
├── .DFM/                 # Forester internal directory
│   ├── database.db       # Repository database
│   ├── objects/          # Object storage
│   └── refs/             # References (branches, tags)
├── .dfmignore           # Ignore file (optional)
└── ...                  # Your project files
```

## 🔒 Security & Reliability  
- Safe commit deletion via reflog  
- Deduplication – identical files stored only once  
- Data integrity – hash verification and checksums  
- Atomic database transactions  
- File locking – prevents conflicts during collaborative work  
