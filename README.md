# HackRF WebUI - Advanced Spectrum Analyzer

![HackRF WebUI](https://img.shields.io/badge/HackRF-WebUI-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![React](https://img.shields.io/badge/react-18+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A powerful web-based spectrum analyzer for HackRF One with real-time visualization, advanced filtering, and signal analysis capabilities.

## ✨ Features

### 🔴 **Real-Time Spectrum Analysis**
- **High-Resolution Display**: 8,192 data points for detailed spectrum visualization
- **Full Frequency Range**: Proper 88-108MHz FM band coverage (or custom ranges)
- **Live WebSocket Streaming**: Stable, crash-resistant data acquisition
- **Interactive Tooltips**: Hover for precise frequency and power readings

### 🎯 **Advanced Signal Filtering**
- **dB Range Filtering**: Highlight signals within specific power ranges when paused
- **Visual Signal Highlighting**: Red overlay for filtered signals with dimmed background
- **Click-to-Analyze**: Click any filtered point for detailed frequency/power information
- **Real-Time Filter Feedback**: Live count of filtered signals

### 📊 **Multiple Display Modes**
- **Spectrum Analyzer**: Traditional line chart with Chart.js
- **Waterfall Display**: Time-based spectrum visualization
- **Dark Theme UI**: Professional interface optimized for long analysis sessions

### ⚙️ **Device Control**
- **Gain Management**: Separate LNA and VGA gain controls
- **Frequency Range**: Configurable start/stop frequencies
- **Device Safety**: Automatic device detection and crash prevention
- **Resource Management**: Clean shutdown and device release

### 🏗️ **Robust Architecture**
- **SDRStreamer**: Dedicated threading architecture preventing HackRF crashes
- **Queue Management**: Optimized data flow with overflow protection
- **Error Recovery**: Automatic reconnection and device reset capabilities
- **Cross-Platform**: Windows (WSL2), macOS, and Linux support

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** with SoapySDR support
- **Node.js 16+** for React frontend
- **HackRF One** with proper drivers
- **Web browser** with WebSocket support

### 1. Install System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y soapysdr-tools python3-soapysdr python3-venv hackrf

# macOS
brew install soapysdr hackrf

# Windows: Install SoapySDR and HackRF drivers from official sources
```

### 2. WSL2 Setup (Windows Users)

Attach HackRF to WSL2:

```powershell
# In PowerShell as Administrator
usbipd list                           # Find HackRF bus ID
usbipd bind --busid <BUS_ID>         # One-time setup
usbipd attach --wsl --busid <BUS_ID>  # Attach to WSL2
```

Verify in WSL2:
```bash
hackrf_info  # Should show device information
```

### 3. Setup Project

```bash
# Clone and enter directory
git clone <repository-url>
cd hackrf_webui_windows

# Create Python environment with system packages
python3 -m venv venv --system-site-packages
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install Python dependencies
pip install -r requirements.txt

# Setup frontend
cd frontend
npm install
cd ..
```

### 4. Run Application

```bash
# Option 1: Start both services
./run.py

# Option 2: Start manually
# Terminal 1 - Backend
python3 -m backend.main

# Terminal 2 - Frontend  
cd frontend && npm start
```

Access at: **http://localhost:3000**

## 🎛️ Usage Guide

### Basic Operation

1. **Connect HackRF**: Ensure device is recognized with `hackrf_info`
2. **Set Frequency Range**: Configure start/stop frequencies (default: 88-108 MHz FM band)
3. **Adjust Gains**: Set LNA (0-40dB) and VGA (0-62dB) for optimal reception
4. **Start Scanning**: Click "Start" to begin real-time spectrum analysis
5. **Pause for Analysis**: Click "Stop" to pause and enable filtering features

### Advanced Signal Analysis

1. **Enable dB Filtering**: Toggle the "Enable dB Filter" switch when paused
2. **Set Filter Range**: Use sliders to define power range (e.g., -60dB to -40dB for strong signals)
3. **Analyze Signals**: Red highlighted points show signals matching your criteria
4. **Click for Details**: Click any red point to see exact frequency and power
5. **Export Data**: Copy frequency/power values for documentation

### Display Modes

- **Spectrum View**: Real-time line chart with filtering capabilities
- **Waterfall View**: Time-based heatmap showing signal activity over time

## 🔧 Configuration

### Frequency Ranges
```python
# Common frequency bands
FM_RADIO = (88e6, 108e6)      # 88-108 MHz
AIRCRAFT = (118e6, 137e6)     # 118-137 MHz  
HAM_2M = (144e6, 148e6)       # 144-148 MHz
WEATHER = (162e6, 163e6)      # 162-163 MHz
```

### Performance Tuning
```python
# In backend/main.py
SAMPLE_RATE = 20e6            # 20 MHz sample rate
BUFFER_SIZE = 256 * 1024      # 256KB buffer
QUEUE_SIZE = 20               # Internal queue size
DECIMATION = 4                # Data decimation factor
```

## 🛠️ Troubleshooting

### Device Issues
```bash
# Check HackRF connection
hackrf_info

# Reset HackRF if frozen
hackrf_reset

# Check USB permissions (Linux)
sudo usermod -a -G plugdev $USER
```

### Python Environment
```bash
# Verify SoapySDR installation
python3 -c "import SoapySDR; print(SoapySDR.Device.enumerate())"

# Recreate environment if needed
rm -rf venv
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
```

### Common Error Messages

| Error | Solution |
|-------|----------|
| "Device busy" | Run `hackrf_reset` or restart application |
| "No devices found" | Check USB connection and drivers |
| "SoapySDR not found" | Reinstall with `--system-site-packages` |
| "Queue overflow" | Normal during heavy processing, data still flows |

## 🏗️ Architecture

### Backend (FastAPI + SoapySDR)
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   HackRF One   │────│   SDRStreamer    │────│   WebSocket     │
│                │    │   (Threading)    │    │   (AsyncIO)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                       ┌──────▼──────┐
                       │ Data Queue  │
                       │ Processing  │
                       └─────────────┘
```

### Frontend (React + Chart.js)
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  ControlPanel   │────│      App.tsx     │────│ SpectrumDisplay │
│                │    │   (WebSocket)    │    │  (Filtering)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                       ┌──────▼──────┐
                       │ WaterfallDisplay│
                       │              │
                       └─────────────┘
```

## 📡 API Reference

### REST Endpoints
- `POST /api/sweep/start` - Start spectrum analysis
- `POST /api/sweep/stop` - Stop spectrum analysis
- `POST /api/gains` - Set LNA/VGA gains
- `GET /api/gains` - Get current gain settings

### WebSocket
- `ws://localhost:8000/ws/spectrum` - Real-time spectrum data stream

### Data Formats
```javascript
// Spectrum Data
{
  "type": "spectrum",
  "frequencies": [88000000, 88001000, ...],  // Hz
  "magnitudes": [-45.2, -67.8, ...],        // dB
  "timestamp": 1623456789000,                // ms
  "center_freq": 98000000                    // Hz
}
```

## 🗺️ Planned Ideas/Roadmap

### 🎯 **Short Term (Next Release)**
- [ ] **Signal Bookmarking**: Save interesting frequencies with notes
- [ ] **Peak Detection**: Automatic identification of signal peaks
- [ ] **Export Functionality**: Save spectrum data as CSV/JSON
- [ ] **Frequency Presets**: Quick selection for common bands (FM, HAM, Aircraft)
- [ ] **Signal Strength History**: Time-based power level tracking

### 🔄 **Medium Term (3-6 months)**
- [ ] **Audio Demodulation**: FM/AM/SSB demodulation with web audio
- [ ] **Multiple Device Support**: Connect multiple HackRF devices
- [ ] **Advanced Triggering**: Start recording based on signal thresholds
- [ ] **Spectrum Comparison**: Overlay multiple spectrum captures
- [ ] **Band Plan Integration**: Show frequency allocations and band names
- [ ] **Signal Classification**: Automatic signal type detection (FM, digital, etc.)

### 🚀 **Long Term (6+ months)**
- [ ] **Plugin Architecture**: Support for custom signal processors
- [ ] **Remote Operation**: Web-based remote HackRF control
- [ ] **Machine Learning**: AI-powered interference detection
- [ ] **Record & Playback**: Save/replay IQ data for analysis
- [ ] **Collaborative Features**: Share spectrum data between users
- [ ] **Mobile Interface**: Responsive design for tablets/phones

### 🔬 **Advanced Features**
- [ ] **Digital Signal Analysis**: APRS, ADS-B, LoRa decoders
- [ ] **Direction Finding**: Phase-coherent multi-device arrays
- [ ] **EMI/EMC Testing**: Electromagnetic compatibility analysis tools
- [ ] **Automated Monitoring**: 24/7 spectrum monitoring with alerts
- [ ] **Database Integration**: Store long-term spectrum data
- [ ] **Real-time Analytics**: Statistical analysis of spectrum usage

### 🌐 **Integration Ideas**
- [ ] **SDR Cloud**: Connect to remote SDR servers worldwide
- [ ] **Weather Integration**: Correlate atmospheric conditions with propagation
- [ ] **Satellite Tracking**: Doppler correction for satellite signals
- [ ] **Contest Logging**: Integration with amateur radio logging software
- [ ] **Scientific Data**: Export for research and academic use

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup
```bash
# Install development dependencies
pip install black pylint pytest
npm install --dev

# Format code
black backend/
npm run format

# Run tests
pytest
npm test
```

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- **SoapySDR** - Cross-platform SDR abstraction layer
- **Chart.js** - Powerful charting library
- **React** - User interface framework
- **FastAPI** - Modern Python web framework
- **HackRF Community** - Hardware and driver support

---

*Built with ❤️ for the SDR and amateur radio community*