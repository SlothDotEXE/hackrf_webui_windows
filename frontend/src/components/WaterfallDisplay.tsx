import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { Paper, Typography, Box, Slider } from '@mui/material';

interface WaterfallData {
  frequencies: number[];
  magnitudes: number[];
  timestamp: number;
}

interface WaterfallDisplayProps {
  data: WaterfallData | null;
  error: string;
  minDb: number;
  maxDb: number;
  onMinDbChange: (value: number) => void;
  onMaxDbChange: (value: number) => void;
}

// Reduce the history size for better performance
const MAX_HISTORY = 100; // Reduced from 200

const WaterfallDisplay: React.FC<WaterfallDisplayProps> = ({ 
  data, 
  error, 
  minDb, 
  maxDb,
  onMinDbChange,
  onMaxDbChange
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const historyRef = useRef<number[][]>([]);
  const [canvasWidth, setCanvasWidth] = useState(800);
  const [shouldUpdate, setShouldUpdate] = useState(false);
  const lastDataRef = useRef<number>(0); // Timestamp-based cache check
  const animationFrameRef = useRef<number>(0);
  
  // Reduce the waterfall rendering resolution for better performance
  const targetWidth = 512; // Reduced resolution
  const targetLineHeight = 4; // Increased line height for better performance

  // Memoize the color mapping function for better performance
  const getColorMap = useMemo(() => {
    // Pre-calculate color map for all possible normalized values (0-255)
    const colorMap = new Array(256);
    
    for (let i = 0; i < 256; i++) {
      const normalized = i / 255;
      
      if (normalized < 0.25) {
        // Black to Blue
        const val = normalized * 4;
        colorMap[i] = [0, 0, Math.floor(val * 255)];
      } else if (normalized < 0.5) {
        // Blue to Cyan
        const val = (normalized - 0.25) * 4;
        colorMap[i] = [0, Math.floor(val * 255), 255];
      } else if (normalized < 0.75) {
        // Cyan to Yellow
        const val = (normalized - 0.5) * 4;
        colorMap[i] = [Math.floor(val * 255), 255, Math.floor((1 - val) * 255)];
      } else {
        // Yellow to Red
        const val = (normalized - 0.75) * 4;
        colorMap[i] = [255, Math.floor((1 - val) * 255), 0];
      }
    }
    
    return colorMap;
  }, []);

  // Get color for a specific magnitude
  const getColor = useCallback((magnitude: number): [number, number, number] => {
    // Normalize magnitude to 0-255 range using current dB range
    const normalized = Math.max(0, Math.min(1, (magnitude - minDb) / (maxDb - minDb)));
    const index = Math.floor(normalized * 255);
    return getColorMap[index];
  }, [minDb, maxDb, getColorMap]);

  // Handle resize event to make canvas responsive
  useEffect(() => {
    const handleResize = () => {
      if (canvasRef.current) {
        // Get the parent element width but cap to prevent excessive rendering
        const parent = canvasRef.current.parentElement;
        if (parent) {
          const width = Math.min(1200, parent.clientWidth);
          setCanvasWidth(width);
          canvasRef.current.width = width;
          setShouldUpdate(true);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize(); // Initial size setup
    
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Downsample data for better performance
  const downsampleData = useCallback((magnitudes: number[]) => {
    if (magnitudes.length <= targetWidth) {
      return [...magnitudes];
    }
    
    // Use averaging for better visual quality
    const result = new Array(targetWidth).fill(0);
    const samplesPerBin = Math.floor(magnitudes.length / targetWidth);
    
    for (let i = 0; i < targetWidth; i++) {
      let sum = 0;
      const startIdx = i * samplesPerBin;
      const endIdx = Math.min(startIdx + samplesPerBin, magnitudes.length);
      
      for (let j = startIdx; j < endIdx; j++) {
        sum += magnitudes[j];
      }
      
      result[i] = sum / (endIdx - startIdx);
    }
    
    return result;
  }, [targetWidth]);

  // Redraw the entire canvas with current history data
  const redrawCanvas = useCallback(() => {
    if (!canvasRef.current || historyRef.current.length === 0) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Calculate how much vertical space each line should take
    const availableHeight = canvas.height - 40; // Reserve space for frequency scale
    const lineHeight = Math.max(targetLineHeight, availableHeight / historyRef.current.length);
    
    // Create a single image data object for the entire waterfall
    const imageData = ctx.createImageData(targetWidth, Math.ceil(availableHeight));
    const imageDataArray = imageData.data;
    
    // Fill the image data all at once
    for (let y = 0; y < historyRef.current.length; y++) {
      const line = historyRef.current[y];
      if (!line || line.length === 0) continue;
      
      const yOffset = Math.min(availableHeight - 1, Math.floor(y * lineHeight));
      
      for (let x = 0; x < line.length; x++) {
        const [r, g, b] = getColor(line[x]);
        
        // Fill multiple rows for each line to achieve desired line height
        for (let h = 0; h < Math.min(targetLineHeight, availableHeight - yOffset); h++) {
          const pixelIndex = ((yOffset + h) * targetWidth + x) * 4;
          imageDataArray[pixelIndex] = r;
          imageDataArray[pixelIndex + 1] = g;
          imageDataArray[pixelIndex + 2] = b;
          imageDataArray[pixelIndex + 3] = 255;
        }
      }
    }
    
    // Draw the entire waterfall image at once
    ctx.putImageData(imageData, 0, 40);
    
    // Draw frequency scale if we have data
    if (historyRef.current.length > 0 && data && data.frequencies && data.frequencies.length > 0) {
      // Draw translucent background for labels
      ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
      ctx.fillRect(0, 0, canvas.width, 30);
      
      ctx.font = '12px Arial';
      ctx.fillStyle = 'white';
      ctx.textAlign = 'center';
      
      // Draw only a few frequency markers to reduce rendering burden
      const markerCount = 5;
      const frequencies = data.frequencies;
      
      for (let i = 0; i <= markerCount; i++) {
        const x = (canvas.width / markerCount) * i;
        const freqIndex = Math.floor((frequencies.length / markerCount) * i);
        if (frequencies[freqIndex] !== undefined) {
          const freq = frequencies[freqIndex];
          const freqMHz = (freq / 1e6).toFixed(1);
          ctx.fillText(`${freqMHz} MHz`, x, 20);
        }
      }
    }
    
    // Set flag to prevent unnecessary redraws
    setShouldUpdate(false);
  }, [getColor, data, targetWidth, targetLineHeight]);

  // Update waterfall when new data arrives
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    
    // Throttle updates based on timestamp to prevent excessive redraws
    const now = Date.now();
    if (now - lastDataRef.current < 100) return; // Limit to ~10 updates per second
    lastDataRef.current = now;
    
    // Downsample the incoming data
    const downsampledData = downsampleData(data.magnitudes);
    
    // Add new data to history
    historyRef.current.unshift(downsampledData);
    
    // Limit history length
    if (historyRef.current.length > MAX_HISTORY) {
      historyRef.current = historyRef.current.slice(0, MAX_HISTORY);
    }
    
    // Schedule a redraw
    setShouldUpdate(true);
  }, [data, downsampleData]);

  // Handle actual drawing logic
  useEffect(() => {
    if (!shouldUpdate) return;
    
    // Use requestAnimationFrame for better performance
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    
    animationFrameRef.current = requestAnimationFrame(() => {
      redrawCanvas();
    });
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [shouldUpdate, redrawCanvas]);

  // Handle dynamic range changes
  useEffect(() => {
    // Redraw when min/max dB changes
    setShouldUpdate(true);
  }, [minDb, maxDb]);

  const handleMinDbChange = (_: Event, value: number | number[]) => {
    onMinDbChange(value as number);
  };

  const handleMaxDbChange = (_: Event, value: number | number[]) => {
    onMaxDbChange(value as number);
  };

  if (error) {
    return (
      <Paper sx={{ p: 2, backgroundColor: 'error.dark' }}>
        <Typography color="error.contrastText">{error}</Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2, height: '60vh' }}>
      <Box sx={{ mb: 2 }}>
        <Typography gutterBottom>Signal Range (dB)</Typography>
        <Box sx={{ px: 2, display: 'flex', gap: 4 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" gutterBottom>
              Minimum (Noise Floor)
            </Typography>
            <Slider
              value={minDb}
              min={-120}
              max={maxDb}
              step={5}
              onChange={handleMinDbChange}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v} dB`}
            />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" gutterBottom>
              Maximum (Peak)
            </Typography>
            <Slider
              value={maxDb}
              min={minDb}
              max={0}
              step={5}
              onChange={handleMaxDbChange}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v} dB`}
            />
          </Box>
        </Box>
      </Box>
      <canvas
        ref={canvasRef}
        width={canvasWidth}
        height={560}
        style={{
          width: '100%',
          height: 'calc(100% - 80px)', // Adjust for the sliders
          objectFit: 'contain',
          backgroundColor: '#000'
        }}
      />
    </Paper>
  );
};

// Use React.memo to prevent unnecessary re-renders
export default React.memo(WaterfallDisplay); 
