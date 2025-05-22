import React, { useRef, useEffect } from 'react';
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
  const MAX_HISTORY = 200; // Number of lines to show in waterfall

  // Color mapping function
  const getColor = (magnitude: number) => {
    // Normalize magnitude to 0-1 range using current dB range
    const normalized = Math.max(0, Math.min(1, (magnitude - minDb) / (maxDb - minDb)));

    // Define color stops for a more pleasing gradient
    if (normalized < 0.25) {
      // Black to Blue
      const val = normalized * 4;
      return [0, 0, Math.floor(val * 255)];
    } else if (normalized < 0.5) {
      // Blue to Cyan
      const val = (normalized - 0.25) * 4;
      return [0, Math.floor(val * 255), 255];
    } else if (normalized < 0.75) {
      // Cyan to Yellow
      const val = (normalized - 0.5) * 4;
      return [Math.floor(val * 255), 255, Math.floor((1 - val) * 255)];
    } else {
      // Yellow to Red
      const val = (normalized - 0.75) * 4;
      return [255, Math.floor((1 - val) * 255), 0];
    }
  };

  useEffect(() => {
    if (!data || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Add new data to history
    historyRef.current.unshift([...data.magnitudes]);
    if (historyRef.current.length > MAX_HISTORY) {
      historyRef.current.pop();
    }

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw waterfall
    const lineHeight = canvas.height / MAX_HISTORY;
    historyRef.current.forEach((line, index) => {
      const imageData = ctx.createImageData(canvas.width, Math.ceil(lineHeight));
      const yOffset = index * lineHeight;

      line.forEach((magnitude, x) => {
        const [r, g, b] = getColor(magnitude);

        // Fill the vertical line for this frequency
        for (let y = 0; y < Math.ceil(lineHeight); y++) {
          const pixelIndex = (y * canvas.width + x) * 4;
          imageData.data[pixelIndex] = r;
          imageData.data[pixelIndex + 1] = g;
          imageData.data[pixelIndex + 2] = b;
          imageData.data[pixelIndex + 3] = 255;
        }
      });

      ctx.putImageData(imageData, 0, yOffset);
    });

    // Draw frequency scale
    if (data.frequencies.length > 0) {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.fillRect(0, 0, canvas.width, 20);
      
      ctx.font = '12px Arial';
      ctx.fillStyle = 'black';
      ctx.textAlign = 'center';
      
      // Draw 5 frequency markers
      for (let i = 0; i < 5; i++) {
        const x = (canvas.width / 4) * i;
        const freqIndex = Math.floor((data.frequencies.length / 4) * i);
        const freq = data.frequencies[freqIndex];
        const freqMHz = (freq / 1e6).toFixed(1);
        ctx.fillText(`${freqMHz} MHz`, x, 15);
      }
    }
  }, [data, minDb, maxDb]);

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
              step={1}
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
              step={1}
              onChange={handleMaxDbChange}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v} dB`}
            />
          </Box>
        </Box>
      </Box>
      <canvas
        ref={canvasRef}
        width={1024}
        height={600}
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

export default WaterfallDisplay; 