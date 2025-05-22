import React, { useCallback, useMemo, useEffect, useRef } from 'react';
import { Paper, Typography, Box } from '@mui/material';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// Reduce animation frame rate for less CPU usage
ChartJS.defaults.animation = {
  duration: 0 
};
ChartJS.defaults.datasets.line.pointRadius = 0;
ChartJS.defaults.elements.line.borderWidth = 1;

interface SpectrumData {
  frequencies: number[];
  magnitudes: number[];
  timestamp: number;
}

interface SpectrumDisplayProps {
  data: SpectrumData | null;
  error: string;
}

const SpectrumDisplay: React.FC<SpectrumDisplayProps> = ({ data, error }) => {
  // Add a ref to the chart for direct access
  const chartRef = useRef<any>(null);
  
  // Display debug info
  useEffect(() => {
    if (data) {
      console.log(`Spectrum data received: ${data.magnitudes.length} points`);
      console.log(`Frequency range: ${data.frequencies[0]/1e6}MHz to ${data.frequencies[data.frequencies.length-1]/1e6}MHz`);
      console.log(`Magnitude range: ${Math.min(...data.magnitudes)}dB to ${Math.max(...data.magnitudes)}dB`);
    }
  }, [data]);

  // Calculate dynamic min/max values for better visualization
  // Only do this calculation if we have data
  const { minPower, maxPower, freqMin, freqMax } = useMemo(() => {
    if (!data || !data.magnitudes.length) {
      return { minPower: -100, maxPower: -20, freqMin: 88, freqMax: 108 };
    }

    // Find a reasonable power range without scanning the whole array
    // Take samples from the array for faster calculation
    const step = Math.max(1, Math.floor(data.magnitudes.length / 20));
    const sampledValues = [];
    for (let i = 0; i < data.magnitudes.length; i += step) {
      sampledValues.push(data.magnitudes[i]);
    }
    
    const min = Math.max(-100, Math.min(...sampledValues) - 5);
    const max = Math.min(-20, Math.max(...sampledValues) + 5);

    // Calculate frequency range
    const fMin = data.frequencies[0] ? data.frequencies[0] / 1e6 : 88;
    const fMax = data.frequencies[data.frequencies.length - 1] ? 
      data.frequencies[data.frequencies.length - 1] / 1e6 : 108;
    
    return { minPower: min, maxPower: max, freqMin: fMin, freqMax: fMax };
  }, [data]);

  // Downsample data for better performance - reduced complexity for reliability
  const { chartFreqs, chartMags } = useMemo(() => {
    if (!data || !data.magnitudes.length) {
      return { chartFreqs: [], chartMags: [] };
    }
    
    // Convert frequencies to MHz for display
    const freqs = data.frequencies.map(f => f / 1e6);
    
    // For reliability, don't downsample - just return the raw data
    return { 
      chartFreqs: freqs, 
      chartMags: data.magnitudes 
    };
  }, [data]);

  // Force chart update when new data arrives
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.update();
    }
  }, [chartFreqs, chartMags]);

  const chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    elements: {
      point: {
        radius: 0
      },
      line: {
        tension: 0.1
      }
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false
    },
    scales: {
      x: {
        type: 'linear',
        display: true,
        position: 'bottom',
        bounds: 'data',
        min: freqMin,
        max: freqMax,
        title: {
          display: true,
          text: 'Frequency (MHz)'
        },
        ticks: {
          maxTicksLimit: 10,
          callback: function(tickValue: string | number) {
            return typeof tickValue === 'number' ? tickValue.toFixed(2) : tickValue;
          }
        }
      },
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        bounds: 'data',
        min: minPower,
        max: maxPower,
        title: {
          display: true,
          text: 'Power (dB)'
        },
        grid: {
          color: 'rgba(255, 255, 255, 0.1)'
        }
      }
    },
    plugins: {
      legend: {
        display: false
      },
      title: {
        display: true,
        text: 'HackRF Spectrum Analyzer'
      },
      tooltip: {
        enabled: true,
        mode: 'index',
        intersect: false,
        callbacks: {
          label: function(context) {
            return `Power: ${context.parsed.y.toFixed(1)} dB`;
          },
          title: function(context) {
            if (context[0]) {
              return `Frequency: ${context[0].label} MHz`;
            }
            return '';
          }
        }
      }
    }
  };

  const chartData = {
    labels: chartFreqs,
    datasets: [
      {
        data: chartMags.map((y, i) => ({ x: chartFreqs[i], y })),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0,  // Reduced tension for more accurate display
        fill: false,
        spanGaps: true
      }
    ]
  };

  if (error) {
    return (
      <Paper sx={{ p: 2, backgroundColor: 'error.dark' }}>
        <Typography color="error.contrastText">{error}</Typography>
      </Paper>
    );
  }

  // If no data yet, show loading message
  if (!data) {
    return (
      <Paper sx={{ p: 2, height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          Waiting for spectrum data...
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2, height: '60vh' }}>
      <Box sx={{ width: '100%', height: '100%', position: 'relative' }}>
        <Line 
          ref={chartRef}
          options={chartOptions} 
          data={chartData} 
        />
        <Box sx={{ position: 'absolute', bottom: 5, right: 10, fontSize: '0.75rem', color: 'text.secondary' }}>
          {data.magnitudes.length} points | {freqMin.toFixed(2)} - {freqMax.toFixed(2)} MHz
        </Box>
      </Box>
    </Paper>
  );
};

// Use React.memo to prevent unnecessary re-renders
export default React.memo(SpectrumDisplay); 