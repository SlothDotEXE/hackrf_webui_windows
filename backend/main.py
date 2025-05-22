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
        active_device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate)
        
        # Set center frequency
        logger.info(f"Setting center frequency to {freq/1e6:.2f}MHz")
        active_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
        
        # Set bandwidth
        logger.info(f"Setting bandwidth to {bandwidth/1e6:.2f}MHz")
        active_device.setBandwidth(SoapySDR.SOAPY_SDR_RX, 0, bandwidth)
        
        # Set gains
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", 32)
        active_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", 20)
        
        # Enable antenna
        active_device.setAntenna(SoapySDR.SOAPY_SDR_RX, 0, "RX")
        
        return True
    except Exception as e:
        logger.error(f"Error configuring device for frequency {freq/1e6:.2f}MHz: {e}")
        return False

async def sweep_frequency():
    """Sweep through frequencies in steps."""
    global current_sweep_config
    
    while is_sweeping:
        current_freq = current_sweep_config["current_freq"]
        
        if current_freq > current_sweep_config["stop_freq"]:
            # Reset to start frequency
            current_sweep_config["current_freq"] = current_sweep_config["start_freq"]
            continue
            
        # Configure device for current frequency
        if configure_device_for_frequency(current_freq):
            # Update timestamp for WebSocket clients
            current_sweep_config["last_update"] = datetime.now().isoformat()
            
            # Move to next frequency step
            current_sweep_config["current_freq"] += current_sweep_config["step_size"]
            
            # Small delay to allow device to settle
            await asyncio.sleep(0.01)
        else:
            logger.error(f"Failed to configure frequency {current_freq/1e6:.2f}MHz")
            await asyncio.sleep(0.1)

@app.post("/api/sweep/start")
async def start_sweep(
    start_freq: float = Body(...),
    stop_freq: float = Body(...),
    sample_rate: float = Body(default=20e6)
):
    """Start spectrum sweep."""
    global active_device, sweep_task, is_sweeping, current_sweep_config
    
    if is_sweeping:
        raise HTTPException(status_code=400, detail="Sweep already in progress")
    
    try:
        # Validate frequency range
        if start_freq >= stop_freq:
            raise HTTPException(status_code=400, detail="Start frequency must be less than stop frequency")
            
        logger.info(f"Starting sweep: {start_freq/1e6:.2f}MHz to {stop_freq/1e6:.2f}MHz")
        
        if not active_device:
            devices = get_hackrf_devices()
            logger.info(f"Found devices: {devices}")
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            try:
                logger.info("Initializing HackRF device...")
                active_device = SoapySDR.Device(dict(driver="hackrf"))
            except Exception as e:
                logger.error(f"Failed to initialize device: {str(e)}")
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
        
        is_sweeping = True
        sweep_task = asyncio.create_task(sweep_frequency())
        
        return {"status": "success", "message": "Sweep started"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error starting sweep: {str(e)}")
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
            sweep_task.cancel()
            sweep_task = None
            
        return {"status": "success", "message": "Sweep stopped"}
        
    except Exception as e:
        logger.error(f"Error stopping sweep: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/spectrum")
async def websocket_spectrum(websocket: WebSocket):
    """WebSocket endpoint for streaming spectrum data."""
    global active_device, is_sweeping, current_sweep_config
    
    await websocket.accept()
    
    try:
        last_update = None
        while True:
            if not is_sweeping:
                await asyncio.sleep(0.1)
                continue
            
            try:
                # Only send new data when frequency has changed
                if current_sweep_config["last_update"] != last_update:
                    # Simulate spectrum data for now
                    # TODO: Implement actual HackRF sampling
                    spectrum_data = np.random.normal(size=1024)
                    
                    await websocket.send_json({
                        "type": "spectrum",
                        "data": spectrum_data.tolist(),
                        "frequency": current_sweep_config["current_freq"],
                        "timestamp": current_sweep_config["last_update"]
                    })
                    
                    last_update = current_sweep_config["last_update"]
                
                await asyncio.sleep(0.01)  # Small delay to prevent CPU overload
                
            except Exception as e:
                logger.error(f"Error in spectrum data streaming: {e}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()

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