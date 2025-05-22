from fastapi import FastAPI, WebSocket, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import SoapySDR
import numpy as np
from typing import List, Optional, Dict
import asyncio
import json
from dataclasses import dataclass, asdict
import logging
from datetime import datetime
from scipy import signal
from dsp import SignalProcessor
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HackRF WebUI")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
active_device: Optional[SoapySDR.Device] = None
sweep_task: Optional[asyncio.Task] = None
is_sweeping = False
current_sweep_config = {
    "start_freq": 0,
    "stop_freq": 0,
    "step_size": 20e6,  # 20MHz steps (HackRF's instantaneous bandwidth)
    "current_freq": 0,
    "sample_rate": 20e6,
    "last_update": None
}

# Add SignalProcessor instance to global state
signal_processor = SignalProcessor(sample_rate=20e6)

@dataclass
class DeviceInfo:
    serial: str
    driver: str
    label: str
    available: bool

def get_hackrf_devices() -> List[DeviceInfo]:
    """List all available HackRF devices."""
    devices = []
    try:
        results = SoapySDR.Device.enumerate({"driver": "hackrf"})
        for result in results:
            # Convert SoapySDRKwargs to dict
            result_dict = {key: result[key] for key in result.keys()}
            device_info = DeviceInfo(
                serial=result_dict.get("serial", "Unknown"),
                driver=result_dict.get("driver", "hackrf"),
                label=result_dict.get("label", "HackRF One"),
                available=True
            )
            devices.append(device_info)
            logger.info(f"Found HackRF device: {device_info}")
    except Exception as e:
        logger.error(f"Error enumerating devices: {e}")
        # Try direct device creation as fallback
        try:
            device = SoapySDR.Device(dict(driver="hackrf"))
            if device:
                device_info = DeviceInfo(
                    serial="Unknown",
                    driver="hackrf",
                    label="HackRF One",
                    available=True
                )
                devices.append(device_info)
                logger.info("Found HackRF device through direct initialization")
        except Exception as direct_error:
            logger.error(f"Direct device creation also failed: {direct_error}")
    return devices

def configure_device_for_frequency(freq: float, bandwidth: float = 20e6):
    """Configure device for a specific frequency."""
    global active_device
    
    try:
        # Set sample rate (must be ≤ bandwidth)
        sample_rate = min(current_sweep_config["sample_rate"], bandwidth)
        print(f"Setting sample rate to {sample_rate/1e6:.2f}MHz")
        active_device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate)
        
        # Set center frequency
        print(f"Setting center frequency to {freq/1e6:.2f}MHz")
        active_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
        
        # Set bandwidth
        print(f"Setting bandwidth to {bandwidth/1e6:.2f}MHz")
        active_device.setBandwidth(SoapySDR.SOAPY_SDR_RX, 0, bandwidth)
        
        # Set gains
        print("Setting gains: LNA=32, VGA=20")
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", 32)
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", 20)
        
        # Enable antenna
        print("Setting antenna to RX")
        active_device.setAntenna(SoapySDR.SOAPY_SDR_RX, 0, "RX")
        
        # Allow device to settle
        time.sleep(0.01)
        
        # Clear any stale data in device buffers
        active_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq + 1)  # Small offset
        time.sleep(0.001)
        active_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)  # Back to desired frequency
        
        print("Device configuration complete")
        return True
    except Exception as e:
        print(f"Error configuring device for frequency {freq/1e6:.2f}MHz: {e}")
        return False

async def sweep_frequency():
    """Sweep through frequencies in steps."""
    global current_sweep_config, active_device, is_sweeping
    
    print("Starting frequency sweep")  # Mandatory print
    
    try:
        while is_sweeping:
            current_freq = current_sweep_config["current_freq"]
            
            if current_freq > current_sweep_config["stop_freq"]:
                # Reset to start frequency
                print("Resetting to start frequency")  # Mandatory print
                current_sweep_config["current_freq"] = current_sweep_config["start_freq"]
                continue
            
            # Configure device for current frequency
            print(f"Sweeping to {current_freq/1e6:.2f}MHz")  # Mandatory print
            if configure_device_for_frequency(current_freq):
                # Move to next frequency step
                current_sweep_config["current_freq"] += current_sweep_config["step_size"]
                # Small delay to allow device to settle
                await asyncio.sleep(0.05)
            else:
                print(f"Failed to configure frequency {current_freq/1e6:.2f}MHz")  # Mandatory print
                await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"Error in sweep: {e}")  # Mandatory print
        is_sweeping = False
    finally:
        print("Sweep task ended")  # Mandatory print

@app.post("/api/sweep/start")
async def start_sweep(
    start_freq: float = Body(...),
    stop_freq: float = Body(...),
    sample_rate: float = Body(default=20e6)
):
    """Start spectrum sweep."""
    global active_device, sweep_task, is_sweeping, current_sweep_config
    
    print(f"Starting sweep from {start_freq/1e6:.2f}MHz to {stop_freq/1e6:.2f}MHz")  # Mandatory print
    
    if is_sweeping:
        raise HTTPException(status_code=400, detail="Sweep already in progress")
    
    try:
        # Validate frequency range
        if start_freq >= stop_freq:
            raise HTTPException(status_code=400, detail="Start frequency must be less than stop frequency")
        
        if not active_device:
            devices = get_hackrf_devices()
            print(f"Found devices: {devices}")  # Mandatory print
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            try:
                print("Initializing HackRF device...")  # Mandatory print
                active_device = SoapySDR.Device(dict(driver="hackrf"))
                print("HackRF device initialized successfully")  # Mandatory print
            except Exception as e:
                print(f"Failed to initialize device: {str(e)}")  # Mandatory print
                raise HTTPException(status_code=500, detail=f"Failed to initialize device: {str(e)}")
        
        # Configure sweep parameters
        current_sweep_config.update({
            "start_freq": start_freq,
            "stop_freq": stop_freq,
            "current_freq": start_freq,
            "sample_rate": sample_rate,
            "step_size": 20e6,  # 20MHz steps
            "last_update": None
        })
        
        print("Configuring initial frequency...")  # Mandatory print
        if not configure_device_for_frequency(start_freq):
            raise HTTPException(status_code=500, detail="Failed to configure initial frequency")
        
        is_sweeping = True
        print("Starting sweep task...")  # Mandatory print
        sweep_task = asyncio.create_task(sweep_frequency())
        print("Sweep task created")  # Mandatory print
        
        return {"status": "success", "message": "Sweep started"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error starting sweep: {str(e)}")  # Mandatory print
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/sweep/stop")
async def stop_sweep():
    """Stop spectrum sweep."""
    global active_device, sweep_task, is_sweeping
    
    if not is_sweeping:
        raise HTTPException(status_code=400, detail="No sweep in progress")
    
    try:
        is_sweeping = False
        if sweep_task:
            await sweep_task
            sweep_task = None
            
        return {"status": "success", "message": "Sweep stopped"}
        
    except Exception as e:
        logger.error(f"Error stopping sweep: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/spectrum")
async def websocket_spectrum(websocket: WebSocket):
    """WebSocket endpoint for streaming spectrum data."""
    global active_device, is_sweeping, current_sweep_config
    
    print("New WebSocket connection attempt")
    await websocket.accept()
    print("WebSocket connection accepted")
    
    # Setup stream once outside the loop
    rx_stream = None
    try:
        if not active_device:
            print("No active device available")
            await websocket.close()
            return
        
        print("Setting up RX stream...")
        
        # Configure stream using setupStream directly without StreamArgs
        rx_stream = active_device.setupStream(SoapySDR.SOAPY_SDR_RX, "CF32", [0])
        
        print("Activating stream...")
        flags = SoapySDR.SOAPY_SDR_HAS_TIME | SoapySDR.SOAPY_SDR_END_BURST
        active_device.activateStream(rx_stream, flags, 0, 8192)
        
        buffer_size = 8192
        buffer = np.zeros(buffer_size, np.complex64)
        
        # Initialize MTU size for optimal transfers
        mtu = active_device.getStreamMTU(rx_stream)
        print(f"Stream MTU: {mtu}")
        
        while True:
            if not is_sweeping:
                await asyncio.sleep(0.1)
                continue
            
            try:
                # Clear any stale data
                _ = active_device.readStream(rx_stream, [buffer], len(buffer), timeoutUs=0)
                
                # Read samples from HackRF with appropriate timeout
                status = active_device.readStream(rx_stream, [buffer], len(buffer), timeoutUs=100000)
                
                if status.ret > 0:
                    print(f"Read {status.ret} samples")
                    
                    # Process samples to get spectrum
                    samples = buffer[:status.ret]
                    
                    # Apply window function and compute FFT
                    windowed = samples * signal.windows.blackman(len(samples))
                    spectrum = np.fft.fftshift(np.fft.fft(windowed))
                    
                    # Convert to power in dB
                    power_db = 20 * np.log10(np.abs(spectrum) + 1e-10)
                    
                    # Reduce number of points for display
                    decimation = 4
                    power_db = power_db[::decimation]  # Use striding instead of reshape for decimation
                    
                    # Calculate frequency points
                    freq_step = current_sweep_config["sample_rate"] / len(samples)
                    freqs = np.arange(
                        current_sweep_config["current_freq"] - current_sweep_config["sample_rate"]/2,
                        current_sweep_config["current_freq"] + current_sweep_config["sample_rate"]/2,
                        freq_step * decimation
                    )
                    
                    # Send data to client
                    await websocket.send_json({
                        "type": "spectrum",
                        "data": power_db.tolist(),
                        "frequencies": freqs.tolist(),
                        "timestamp": datetime.now().isoformat()
                    })
                    print("Sent spectrum data to client")
                    
                    # Small delay to prevent buffer overflow
                    await asyncio.sleep(0.001)
                    
                else:
                    print(f"readStream returned {status.ret}")
                    if status.ret == SoapySDR.SOAPY_SDR_TIMEOUT:
                        await asyncio.sleep(0.001)
                    elif status.ret == SoapySDR.SOAPY_SDR_OVERFLOW:
                        # On overflow, clear the buffer and wait briefly
                        _ = active_device.readStream(rx_stream, [buffer], len(buffer), timeoutUs=0)
                        await asyncio.sleep(0.005)
                    else:
                        await asyncio.sleep(0.001)
                
            except Exception as e:
                print(f"Error in spectrum data streaming: {e}")
                break
                
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if rx_stream:
            try:
                print("Cleaning up stream...")
                active_device.deactivateStream(rx_stream)
                active_device.closeStream(rx_stream)
                print("Stream cleanup complete")
            except Exception as e:
                print(f"Error cleaning up stream: {e}")
        await websocket.close()
        print("WebSocket connection closed")

@app.post("/api/tune")
async def tune_frequency(freq: float, sample_rate: float = 2e6):
    """Tune to a specific frequency for FM demodulation."""
    global active_device, is_sweeping
    
    if is_sweeping:
        await stop_sweep()
    
    try:
        if not active_device:
            devices = get_hackrf_devices()
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            active_device = SoapySDR.Device(dict(driver="hackrf"))
        
        # Configure device for FM reception
        active_device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate)
        active_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", 32)
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", 20)
        
        return {"status": "success", "message": f"Tuned to {freq/1e6:.2f} MHz"}
        
    except Exception as e:
        logger.error(f"Error tuning frequency: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gains")
async def set_gains(gains: Dict[str, int] = Body(...)):
    """Set device gain values."""
    global active_device
    
    try:
        if not active_device:
            raise HTTPException(status_code=400, detail="No active device")
            
        logger.info(f"Setting gains: {gains}")
        
        # Update each gain value
        for gain_name, value in gains.items():
            if gain_name in ["LNA", "VGA"]:  # Only allow these gain controls
                try:
                    active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, gain_name, value)
                    logger.info(f"Set {gain_name} gain to {value}")
                except Exception as e:
                    logger.error(f"Failed to set {gain_name} gain: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Failed to set {gain_name} gain: {str(e)}")
        
        # Return current gain values
        current_gains = {
            "LNA": active_device.getGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA"),
            "VGA": active_device.getGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA")
        }
        
        return {"status": "success", "gains": current_gains}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error setting gains: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/api/gains")
async def get_gains():
    """Get current device gain values."""
    global active_device
    
    try:
        if not active_device:
            raise HTTPException(status_code=400, detail="No active device")
            
        # Get current gain values
        current_gains = {
            "LNA": active_device.getGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA"),
            "VGA": active_device.getGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA")
        }
        
        return {"status": "success", "gains": current_gains}
        
    except Exception as e:
        logger.error(f"Error getting gains: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 