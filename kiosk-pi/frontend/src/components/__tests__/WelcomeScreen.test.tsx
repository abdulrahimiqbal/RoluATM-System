import { render, screen } from '@testing-library/react';
import { describe, it, expect } from '@jest/globals';
import WelcomeScreen from '../WelcomeScreen';

describe('WelcomeScreen', () => {
  it('renders welcome message', () => {
    render(<WelcomeScreen onStart={jest.fn()} />);
    
    expect(screen.getByText(/RoluATM/i)).toBeInTheDocument();
    expect(screen.getByText(/World ID Verified/i)).toBeInTheDocument();
  });

  it('calls onStart when touch anywhere button is clicked', () => {
    const mockOnStart = jest.fn();
    render(<WelcomeScreen onStart={mockOnStart} />);
    
    const startButton = screen.getByText(/Touch anywhere to start/i);
    startButton.click();
    
    expect(mockOnStart).toHaveBeenCalledTimes(1);
  });

  it('displays coin mechanism status', () => {
    render(<WelcomeScreen onStart={jest.fn()} />);
    
    expect(screen.getByText(/Insert coins to receive quarters/i)).toBeInTheDocument();
  });
}); 