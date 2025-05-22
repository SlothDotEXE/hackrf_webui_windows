import React from 'react';
import { Paper, Typography } from '@mui/material';
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
  // Calculate dynamic min/max values for better visualization
  const minPower = data?.magnitudes ? Math.max(-100, Math.min(...data.magnitudes) - 10) : -100;
  const maxPower = data?.magnitudes ? Math.min(-20, Math.max(...data.magnitudes) + 10) : -20;

  const chartOptions: ChartOptions<'line'> = {
    responsive: true,
    animation: {
      duration: 0
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
        min: data?.frequencies[0] ? data.frequencies[0] / 1e6 : 88,
        max: data?.frequencies[data.frequencies.length - 1] ? data.frequencies[data.frequencies.length - 1] / 1e6 : 108,
        title: {
          display: true,
          text: 'Frequency (MHz)'
        },
        ticks: {
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
    labels: data?.frequencies.map(f => f / 1e6) || [],
    datasets: [
      {
        data: data?.magnitudes || [],
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        pointRadius: 0,
        tension: 0.1,
        fill: false
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

  return (
    <Paper sx={{ p: 2, height: '60vh' }}>
      <Line options={chartOptions} data={chartData} />
    </Paper>
  );
};

export default SpectrumDisplay; 