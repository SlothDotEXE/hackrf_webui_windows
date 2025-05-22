import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Container,
  CssBaseline,
  ThemeProvider,
  createTheme,
  ToggleButtonGroup,
  ToggleButton,
  Tooltip
} from '@mui/material';
import SpectrumDisplay from './components/SpectrumDisplay';
import WaterfallDisplay from './components/WaterfallDisplay';
import ControlPanel from './components/ControlPanel';
import TimelineIcon from '@mui/icons-material/Timeline';
import WaterfallChartIcon from '@mui/icons-material/WaterfallChart';
import axios, { AxiosError } from 'axios';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
  },
});

interface SpectrumData {
  frequencies: number[];
  magnitudes: number[];
  timestamp: number;
}

type DisplayMode = 'spectrum' | 'waterfall';

function App() {
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [startFreq, setStartFreq] = useState<number>(88e6); // 88 MHz (FM Radio start)
  const [stopFreq, setStopFreq] = useState<number>(108e6); // 108 MHz (FM Radio end)
  const [lnaGain, setLnaGain] = useState<number>(32); // Default LNA gain
  const [vgaGain, setVgaGain] = useState<number>(20); // Default VGA gain
  const [spectrumData, setSpectrumData] = useState<SpectrumData | null>(null);
  const [error, setError] = useState<string>('');
  const [displayMode, setDisplayMode] = useState<DisplayMode>('spectrum');
  const [minDb, setMinDb] = useState<number>(-100); // Default minimum dB
  const [maxDb, setMaxDb] = useState<number>(-20); // Default maximum dB
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (isRunning && !wsRef.current) {
      console.log("Creating new WebSocket connection...");
      
      // Create WebSocket connection
      const ws = new WebSocket('ws://localhost:8000/ws/spectrum');
      
      // Track connection state
      let connectionActive = false;
      
      // Connection opened
      ws.onopen = () => {
        console.log('WebSocket connection established');
        connectionActive = true;
      };
      
      ws.onmessage = (event) => {
        try {
          // Check if message is a ping request
          if (event.data === "ping") {
            ws.send("pong");
            return;
          }
          
          const data = JSON.parse(event.data);
          if (data.type === 'spectrum') {
            // Verify data has needed properties
            if (data.frequencies && data.magnitudes && 
                Array.isArray(data.frequencies) && 
                Array.isArray(data.magnitudes) && 
                data.frequencies.length > 0 && 
                data.magnitudes.length > 0) {
              
              console.log(`Received spectrum data: ${data.magnitudes.length} points`);
              
              setSpectrumData({
                frequencies: data.frequencies,
                magnitudes: data.magnitudes,
                timestamp: Date.now()
              });
              
              // Clear any previous errors
              if (error) setError('');
            } else {
              console.warn('Received malformed spectrum data', data);
            }
          } else if (data.type === 'error') {
            // Handle error messages from backend
            console.error('Backend error:', data.message);
            setError(data.message || 'Unknown error from HackRF device');
            
            // If we get a resource busy error, we should stop the analyzer
            if (data.message && data.message.includes('busy')) {
              setIsRunning(false);
            }
          }
        } catch (err) {
          console.error('Error parsing WebSocket data:', err);
          setError('Error parsing spectrum data');
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error');
      };

      ws.onclose = (event) => {
        console.log(`WebSocket connection closed: ${event.code} ${event.reason}`);
        wsRef.current = null;
        
        // Auto-reconnect if unexpected close and still running
        if (connectionActive && isRunning && event.code !== 1000) {
          console.log('Attempting to reconnect in 1 second...');
          setTimeout(() => {
            if (isRunning) {
              console.log('Reconnecting WebSocket...');
              // Trigger effect to reconnect
              const reconnect = () => {
                setIsRunning(isRunning);
              };
              reconnect();
            }
          }, 1000);
        }
      };

      wsRef.current = ws;

      // Cleanup function
      return () => {
        if (wsRef.current) {
          console.log("Closing WebSocket connection...");
          try {
            wsRef.current.close(1000, "Client initiated close");
          } catch (e) {
            console.error("Error closing WebSocket:", e);
          }
          wsRef.current = null;
        }
      };
    } else if (!isRunning && wsRef.current) {
      // Close WebSocket when stopping
      console.log("Stopping spectrum analyzer, closing WebSocket...");
      try {
        wsRef.current.close(1000, "Client stopped analyzer");
      } catch (e) {
        console.error("Error closing WebSocket:", e);
      }
      wsRef.current = null;
      
      // Reset spectrum data when stopping
      setSpectrumData(null);
    }
  }, [isRunning, error]);

  const handleStartStop = async () => {
    try {
      if (!isRunning) {
        await axios.post('http://localhost:8000/api/sweep/start', {
          start_freq: startFreq,
          stop_freq: stopFreq,
          sample_rate: 20e6, // Fixed at 20 MHz
          gain_db: lnaGain // Using LNA gain as primary gain
        });
      } else {
        await axios.post('http://localhost:8000/api/sweep/stop');
      }
      setIsRunning(!isRunning);
      setError('');
    } catch (err) {
      const errorMessage = err instanceof AxiosError 
        ? err.response?.data?.message || 'Failed to start/stop HackRF'
        : 'Failed to start/stop HackRF';
      setError(errorMessage);
      console.error('Error controlling HackRF:', err);
    }
  };

  // Update gains when they change
  useEffect(() => {
    if (isRunning) {
      axios.post('http://localhost:8000/api/gains', {
        LNA: lnaGain,
        VGA: vgaGain
      }).catch(err => {
        console.error('Error updating gains:', err);
      });
    }
  }, [lnaGain, vgaGain, isRunning]);

  const handleDisplayModeChange = (
    _: React.MouseEvent<HTMLElement>,
    newMode: DisplayMode,
  ) => {
    if (newMode !== null) {
      setDisplayMode(newMode);
    }
  };

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Container maxWidth="xl">
        <Box sx={{ my: 4 }}>
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
            <ToggleButtonGroup
              value={displayMode}
              exclusive
              onChange={handleDisplayModeChange}
              aria-label="display mode"
            >
              <Tooltip title="Spectrum Analyzer" arrow>
                <ToggleButton value="spectrum" aria-label="spectrum view">
                  <TimelineIcon />
                </ToggleButton>
              </Tooltip>
              <Tooltip title="Waterfall Display" arrow>
                <ToggleButton value="waterfall" aria-label="waterfall view">
                  <WaterfallChartIcon />
                </ToggleButton>
              </Tooltip>
            </ToggleButtonGroup>
          </Box>
          
          {displayMode === 'spectrum' ? (
            <SpectrumDisplay
              data={spectrumData}
              error={error}
            />
          ) : (
            <WaterfallDisplay
              data={spectrumData}
              error={error}
              minDb={minDb}
              maxDb={maxDb}
              onMinDbChange={setMinDb}
              onMaxDbChange={setMaxDb}
            />
          )}

          <ControlPanel
            isRunning={isRunning}
            startFreq={startFreq}
            stopFreq={stopFreq}
            lnaGain={lnaGain}
            vgaGain={vgaGain}
            onStartStop={handleStartStop}
            onStartFreqChange={setStartFreq}
            onStopFreqChange={setStopFreq}
            onLnaGainChange={setLnaGain}
            onVgaGainChange={setVgaGain}
          />
        </Box>
      </Container>
    </ThemeProvider>
  );
}

export default App;
