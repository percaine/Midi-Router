from flask import Flask, render_template_string, request, redirect, url_for, jsonify
import mido
import threading
import time
import sys
import os
import importlib
import subprocess
import platform

app = Flask(__name__)

manual_mode = False

connection_log = set()
manual_connection_log = set()
port_names = []
last_ports = set()

# MIDI Connection Management
active_midi_connections = {}  # Store active MIDI port objects
midi_threads = {}  # Store MIDI forwarding threads
auto_connections = set()  # Store automatically created connections
usb_device_patterns = ['USB', 'MIDI', 'Controller', 'Keyboard', 'Piano', 'Synth', 'Drum', 'Arturia', 'Roland', 'Yamaha', 'Korg', 'Novation', 'Native Instruments']

# Device order tracking
connected_usb_devices = []  # List to maintain the order of connected USB devices

# Monitor thread control
monitor_thread = None
monitor_running = True

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MIDI Router Web GUI</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
        .connection-line {
            background: linear-gradient(90deg, #3b82f6, #8b5cf6);
            height: 2px;
            border-radius: 1px;
        }
        .auto-connection-line {
            background: linear-gradient(90deg, #10b981, #3b82f6);
            height: 2px;
            border-radius: 1px;
        }
        .pulse-dot {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .port-card {
            transition: all 0.3s ease;
        }
        .port-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }
        #notification-container {
            position: fixed;
            top: 1rem;
            right: 1rem;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        /* Custom toggle switch */
        .switch {
          position: relative;
          display: inline-block;
          width: 40px;
          height: 20px;
        }
        .switch input { 
          opacity: 0;
          width: 0;
          height: 0;
        }
        .slider {
          position: absolute;
          cursor: pointer;
          top: 0; left: 0; right: 0; bottom: 0;
          background-color: #ccc;
          transition: .4s;
          border-radius: 20px;
        }
        .slider:before {
          position: absolute;
          content: "";
          height: 14px;
          width: 14px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: .4s;
          border-radius: 50%;
        }
        input:checked + .slider {
          background-color: #4ade80;
        }
        input:checked + .slider:before {
          transform: translateX(20px);
        }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="container mx-auto px-6 py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-8">
            <!-- Left side - empty now -->
            <div class="w-1/4"></div>
            
            <!-- Center - title moved here -->
            <div class="flex flex-col items-center justify-center w-1/2">
                <h1 class="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent text-center">
                    MIDI Router
                </h1>
                <p class="text-gray-400 text-sm text-center">USB MIDI HOST</p>
            </div>
            
            <!-- Right side - controls -->
            <div class="flex items-center space-x-5 w-1/4 justify-end">
                <!-- Manual mode toggle -->
                <label for="manual-mode-toggle" class="flex items-center cursor-pointer select-none text-gray-300 text-sm space-x-2">
                    <span>Manual Mode</span>
                    <div class="switch">
                        <input type="checkbox" id="manual-mode-toggle" />
                        <span class="slider"></span>
                    </div>
                </label>
                
                <button id="refresh-button" onclick="refreshData()" class="bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg transition-colors flex items-center space-x-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                    </svg>
                    <span>Refresh</span>
                </button>
            </div>
        </div>

        <!-- Connection Status -->
        <div class="mb-6">
            <div id="connection-status" class="bg-red-800 border border-red-600 rounded-lg p-4 flex items-center space-x-3">
                <div class="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                <span>Connecting to MIDI server...</span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Available Ports -->
            <div class="lg:col-span-1">
                <div class="bg-gray-800 rounded-xl p-6 h-fit">
                    <div class="flex items-center space-x-2 mb-4">
                        <svg class="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>
                        </svg>
                        <h2 class="text-xl font-semibold">DEVICES</h2>
                        <span id="port-count" class="bg-blue-500 text-xs px-2 py-1 rounded-full">0</span>
                    </div>
                    <div id="port-list" class="space-y-2">
                        <div class="text-center py-4 text-gray-500">
                            <div class="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2"></div>
                            <p class="text-sm">Loading ports...</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Connection Management -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Create Connection -->
                <div class="bg-gray-800 rounded-xl p-6">
                    <div class="flex items-center space-x-2 mb-4">
                        <svg class="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>
                        </svg>
                        <h2 class="text-xl font-semibold">Connect</h2>
                    </div>
                    <form onsubmit="handleConnect(event)" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <select name="from" id="from-port" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                    <option value="">-- Select Input Source --</option>
                                </select>
                            </div>
                            <div>
                                <select name="to" id="to-port" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                    <option value="">-- Select Output Destination --</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" class="w-full bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 px-4 py-2 rounded-lg transition-all duration-200 font-medium">
                            Connect
                        </button>
                    </form>
                </div>
        
                <!-- Disconnect Connection Section -->
                <div class="bg-gray-800 rounded-xl p-6">
                    <div class="flex items-center space-x-2 mb-4">
                        <svg class="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                        <h2 class="text-xl font-semibold">Disconnect</h2>
                    </div>
                    <form onsubmit="handleDisconnect(event)" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <select name="from" id="disconnect-from-port" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-red-500 focus:border-transparent">
                                    <option value="">-- Select Input Source --</option>
                                </select>
                            </div>
                            <div>
                                <select name="to" id="disconnect-to-port" class="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-red-500 focus:border-transparent">
                                    <option value="">-- Select Output Destination --</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" class="w-full bg-gradient-to-r from-red-500 to-purple-600 hover:from-red-600 hover:to-purple-700 px-4 py-2 rounded-lg transition-all duration-200 font-medium">
                            Disconnect
                        </button>
                    </form>
                </div>

                <!-- Active Connections -->
                <div class="bg-gray-800 rounded-xl p-6">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center space-x-2">
                            <svg class="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
                            </svg>
                            <h2 class="text-xl font-semibold">Active Connections</h2>
                            <span id="connection-count" class="bg-purple-500 text-xs px-2 py-1 rounded-full">0</span>
                        </div>
                    </div>
                    <div id="connection-list" class="space-y-3">
                    </div>
                    <div id="no-connections" class="text-center py-8 text-gray-500">
                        <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
                        </svg>
                        <p>No active connections</p>
                        <p class="text-sm">USB devices auto-connect when plugged in</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div id="notification-container"></div>
    <script>
        let serverConnected = false;
        let retryCount = 0;
        const maxRetries = 5;

        async function fetchData(showNotificationOnError = true) {
            try {
                const response = await fetch('/status', { method: 'GET' });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                updateConnectionStatus(true);
                updatePortList(data.input_ports, data.output_ports);
                updateConnectionList(data.connections, data.auto_connections, data.manual_connections);
                updateDisconnectDropdowns(data.connections);

                const manualModeToggle = document.getElementById('manual-mode-toggle');
                if (manualModeToggle && manualModeToggle.checked !== data.manual_mode) {
                    manualModeToggle.checked = data.manual_mode;
                }
            } catch (error) {
                console.error('Error fetching data:', error);
                retryCount++;
                updateConnectionStatus(false);
                updatePortList([], []);
                updateConnectionList([], [], []);
                updateDisconnectDropdowns([]);

                if (showNotificationOnError && retryCount <= maxRetries) {
                    showNotification(`Server connection failed, retrying... (${retryCount}/${maxRetries})`, 'error');
                } else if (showNotificationOnError) {
                    showNotification('Running in disconnected mode', 'info');
                }
            }
        }

        function updateConnectionStatus(connected) {
            const statusDiv = document.getElementById('connection-status');
            if (connected) {
                statusDiv.className = 'bg-green-800 border border-green-600 rounded-lg p-4 flex items-center space-x-3';
                statusDiv.innerHTML = `
                    <div class="w-3 h-3 bg-green-500 rounded-full"></div>
                    <span>Connected to MIDI server</span>
                `;
                serverConnected = true;
                retryCount = 0;
            } else {
                statusDiv.className = 'bg-red-800 border border-red-600 rounded-lg p-4 flex items-center space-x-3';
                statusDiv.innerHTML = `
                    <div class="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                    <span>Cannot connect to MIDI server</span>
                `;
                serverConnected = false;
            }
        }

        function updatePortList(inputPorts, outputPorts) {
            const portList = document.getElementById('port-list');
            const portCount = document.getElementById('port-count');
            const fromSelect = document.getElementById('from-port');
            const toSelect = document.getElementById('to-port');
            const disconnectFromSelect = document.getElementById('disconnect-from-port');
            const disconnectToSelect = document.getElementById('disconnect-to-port');

            const currentFrom = fromSelect.value;
            const currentTo = toSelect.value;
            const currentDisconnectFrom = disconnectFromSelect.value;
            const currentDisconnectTo = disconnectToSelect.value;

            const totalPorts = [...new Set([...inputPorts, ...outputPorts])].length;
            portCount.textContent = totalPorts;

            portList.innerHTML = '';
            fromSelect.innerHTML = '<option value="">-- Select Input Source --</option>';
            toSelect.innerHTML = '<option value="">-- Select Output Destination --</option>';

            const allPorts = [...new Set([...inputPorts, ...outputPorts])];

            if (allPorts.length === 0) {
                portList.innerHTML = `
                    <div class="text-center py-4 text-gray-500">
                        <p class="text-sm">No available MIDI devices detected</p>
                    </div>
                `;
                return;
            }

            allPorts.forEach(port => {
                const isInput = inputPorts.includes(port);
                const isOutput = outputPorts.includes(port);
                const portType = isInput && isOutput ? 'Input/Output' : isInput ? 'Input' : 'Output';
                const portColor = isInput && isOutput ? 'bg-green-400' : isInput ? 'bg-blue-400' : 'bg-purple-400';

                const isThrough = port.toLowerCase().includes('through') || port.toLowerCase().includes('thru');
                const isUSB = !isThrough && (
                    port.toLowerCase().includes('usb') ||
                    ['arturia', 'roland', 'yamaha', 'korg', 'novation', 'native instruments', 'controller', 'keyboard'].some(brand =>
                        port.toLowerCase().includes(brand.toLowerCase())
                    )
                );
                const deviceType = isThrough ? 'Through' : isUSB ? 'USB' : 'MIDI';
                const deviceColor = isThrough ? 'bg-blue-600' : isUSB ? 'bg-green-600' : 'bg-gray-600';

                const portCard = document.createElement('div');
                portCard.className = 'port-card bg-gray-700 p-3 rounded-lg flex items-center justify-between';
                portCard.innerHTML = `
                    <div class="flex items-center space-x-3">
                        <div class="w-2 h-2 ${portColor} rounded-full"></div>
                        <div>
                            <div class="text-sm font-medium flex items-center space-x-2">
                                <span>${port}</span>
                                <span class="text-xs ${deviceColor} px-1 py-0.5 rounded">${deviceType}</span>
                            </div>
                            <div class="text-xs text-gray-400">${portType}</div>
                        </div>
                    </div>
                `;
                portList.appendChild(portCard);
            });

            inputPorts.forEach(port => {
                const fromOption = document.createElement('option');
                fromOption.value = port;
                fromOption.textContent = port;
                if (port === currentFrom) fromOption.selected = true;
                fromSelect.appendChild(fromOption);
            });

            outputPorts.forEach(port => {
                const toOption = document.createElement('option');
                toOption.value = port;
                toOption.textContent = port;
                if (port === currentTo) toOption.selected = true;
                toSelect.appendChild(toOption);
            });
        }

        function updateDisconnectDropdowns(connections) {
            const disconnectFromSelect = document.getElementById('disconnect-from-port');
            const disconnectToSelect = document.getElementById('disconnect-to-port');

            const currentDisconnectFrom = disconnectFromSelect.value;
            const currentDisconnectTo = disconnectToSelect.value;

            disconnectFromSelect.innerHTML = '<option value="">-- Select Input Source --</option>';
            disconnectToSelect.innerHTML = '<option value="">-- Select Output Destination --</option>';

            const inputsSet = new Set();
            const outputsSet = new Set();

            connections.forEach(connection => {
                inputsSet.add(connection[0]);
                outputsSet.add(connection[1]);
            });

            inputsSet.forEach(port => {
                const option = document.createElement('option');
                option.value = port;
                option.textContent = port + ' (connected)';
                option.classList.add('font-semibold', 'text-blue-300');
                if (port === currentDisconnectFrom) option.selected = true;
                disconnectFromSelect.appendChild(option);
            });

            outputsSet.forEach(port => {
                const option = document.createElement('option');
                option.value = port;
                option.textContent = port + ' (connected)';
                option.classList.add('font-semibold', 'text-purple-300');
                if (port === currentDisconnectTo) option.selected = true;
                disconnectToSelect.appendChild(option);
            });
        }

        function updateConnectionList(connections, autoConnections, manualConnections) {
            const connectionList = document.getElementById('connection-list');
            const connectionCount = document.getElementById('connection-count');
            const noConnections = document.getElementById('no-connections');

            connectionCount.textContent = connections.length;
            connectionList.innerHTML = '';

            if (connections.length === 0) {
                noConnections.style.display = 'block';
            } else {
                noConnections.style.display = 'none';
                connections.forEach(connection => {
                    const isAutoConnection = autoConnections.some(auto =>
                        auto[0] === connection[0] && auto[1] === connection[1]
                    );

                    const shortenName = (name) => {
                        return name.replace(/^USB MIDI:USB MIDI /, '').replace(/^MIDI Through:/, '');
                    };

                    const connectionCard = document.createElement('div');
                    connectionCard.className = 'bg-gray-700 p-4 rounded-lg';
                    connectionCard.innerHTML = `
                        <div class="flex items-center justify-between">
                            <div class="flex items-center space-x-4 flex-1">
                                <div class="bg-blue-500 px-3 py-1 rounded-full text-xs font-medium max-w-xs truncate">
                                    ${shortenName(connection[0])}
                                </div>
                                <div class="flex items-center space-x-2">
                                    <div class="${isAutoConnection ? 'auto-connection-line' : 'connection-line'} w-8"></div>
                                    <svg class="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                                    </svg>
                                    <div class="${isAutoConnection ? 'auto-connection-line' : 'connection-line'} w-8"></div>
                                </div>
                                <div class="bg-purple-500 px-3 py-1 rounded-full text-xs font-medium max-w-xs truncate">
                                    ${shortenName(connection[1])}
                                </div>
                            </div>
                            <div class="flex items-center space-x-2">
                                <button onclick="disconnectConnection('${connection[0]}', '${connection[1]}')" class="text-red-400 hover:text-red-300 p-1" title="Disconnect">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    `;
                    connectionList.appendChild(connectionCard);
                });
            }
        }

        async function handleConnect(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const fromPort = formData.get('from');
            const toPort = formData.get('to');

            if (!fromPort || !toPort) {
                showNotification('Please select both input and output ports', 'error');
                return;
            }

            if (fromPort === toPort) {
                showNotification('Input and output ports cannot be the same', 'error');
                return;
            }

            if (!serverConnected) {
                showNotification('Demo mode: Connection would be created in real server', 'info');
                return;
            }

            try {
                const response = await fetch('/connect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `from=${encodeURIComponent(fromPort)}&to=${encodeURIComponent(toPort)}`
                });
                if (response.ok) {
                    showNotification('MIDI connection created successfully!', 'success');
                    fetchData();
                } else {
                    showNotification('Failed to create connection', 'error');
                }
            } catch (error) {
                console.error('Error creating connection:', error);
                showNotification('Error creating connection', 'error');
            }
        }

        async function handleDisconnect(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const fromPort = formData.get('from');
            const toPort = formData.get('to');

            if (!fromPort || !toPort) {
                showNotification('Please select both input and output ports', 'error');
                return;
            }

            if (!serverConnected) {
                showNotification('Demo mode: Connection would be disconnected in real server', 'info');
                return;
            }

            try {
                const response = await fetch('/disconnect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `from=${encodeURIComponent(fromPort)}&to=${encodeURIComponent(toPort)}`
                });
                if (response.ok) {
                    showNotification('MIDI connection disconnected', 'info');
                    fetchData();
                } else {
                    showNotification('Failed to disconnect', 'error');
                }
            } catch (error) {
                console.error('Error disconnecting:', error);
                showNotification('Error disconnecting', 'error');
            }
        }

        async function disconnectConnection(fromPort, toPort) {
            if (!serverConnected) {
                showNotification('Demo mode: Connection would be disconnected in real server', 'info');
                return;
            }

            try {
                const response = await fetch('/disconnect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `from=${encodeURIComponent(fromPort)}&to=${encodeURIComponent(toPort)}`
                });
                if (response.ok) {
                    showNotification('MIDI connection disconnected', 'info');
                    fetchData();
                } else {
                    showNotification('Failed to disconnect', 'error');
                }
            } catch (error) {
                console.error('Error disconnecting:', error);
                showNotification('Error disconnecting', 'error');
            }
        }

        function refreshData() {
            fetchData(false);
        }

        function showNotification(message, type) {
            if (message === 'Data refreshed') return;
            const container = document.getElementById('notification-container');
            const notification = document.createElement('div');
            notification.className = `px-4 py-2 rounded-lg text-white z-50 transition-all duration-300 ${
                type === 'success' ? 'bg-green-500' :
                type === 'error' ? 'bg-red-500' : 'bg-blue-500'
            }`;
            notification.textContent = message;
            container.appendChild(notification);
            setTimeout(() => { notification.remove(); }, 3000);
        }

        document.getElementById('manual-mode-toggle').addEventListener('change', async function() {
            try {
                const newValue = this.checked;
                const response = await fetch('/toggle_manual_mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ manual_mode: newValue })
                });
                if (response.ok) {
                    const data = await response.json();
                    showNotification(`Manual mode ${data.manual_mode ? 'enabled' : 'disabled'}`, 'info');
                    fetchData(false);
                } else {
                    showNotification('Failed to toggle manual mode', 'error');
                    this.checked = !newValue; // revert toggle on failure
                }
            } catch (err) {
                showNotification('Error toggling manual mode', 'error');
                this.checked = !this.checked; // revert toggle on error
            }
        });

        // Initial connection status and fetch
        updateConnectionStatus(false);
        fetchData();

        setInterval(() => {
            if (retryCount <= maxRetries) fetchData(false);
        }, 2000);
    </script>
</body>
</html>
"""

def is_usb_midi_device(port_name):
    if is_through_midi_device(port_name):
        return False
    port_lower = port_name.lower()
    for pattern in usb_device_patterns:
        if pattern.lower() in port_lower:
            return True
    manufacturers = [
        'arturia', 'roland', 'yamaha', 'korg', 'novation',
        'native instruments', 'akai', 'm-audio', 'behringer',
        'focusrite', 'presonus', 'steinberg'
    ]
    for manufacturer in manufacturers:
        if manufacturer in port_lower:
            return True
    return False

def is_through_midi_device(port_name):
    port_lower = port_name.lower()
    through_patterns = ['through', 'thru', 'midi through', 'midi thru']
    for pattern in through_patterns:
        if pattern in port_lower:
            return True
    return False

def should_show_port(port_name):
    port_lower = port_name.lower()
    if 'rtmidi' in port_lower:
        return False
    if is_usb_midi_device(port_name):
        return True
    if is_through_midi_device(port_name):
        return True
    return False

def should_auto_connect_port(port_name):
    global manual_mode
    # Only auto-connect USB devices if manual mode is OFF
    if manual_mode:
        return False
    return is_usb_midi_device(port_name)

def filter_ports(ports):
    return [port for port in ports if should_show_port(port)]

def update_port_list():
    global port_names, last_ports, manual_mode, connected_usb_devices
    try:
        current_inputs = filter_ports(mido.get_input_names())
        current_outputs = filter_ports(mido.get_output_names())
        current_ports = set(current_inputs + current_outputs)
        
        if current_ports != last_ports:
            port_names = list(current_ports)
            removed_ports = last_ports - current_ports
            new_ports = current_ports - last_ports

            # Update the connected_usb_devices list
            # First remove any devices that are no longer connected
            if removed_ports:
                for port in removed_ports:
                    if port in connected_usb_devices:
                        connected_usb_devices.remove(port)
                        print(f"Removed {port} from connected devices list")
                
                # Check if USB devices were unplugged
                usb_removed_ports = [p for p in removed_ports if is_usb_midi_device(p)]
                if usb_removed_ports:
                    cleanup_auto_connections()
                    
                    # If in manual mode and ANY USB device was unplugged, switch back to auto mode
                    if manual_mode:
                        print("USB device unplugged in manual mode, switching back to auto mode")
                        switch_to_auto_mode()
                else:
                    print(f"Non-USB devices unplugged: {removed_ports}")
            
            # Add any new USB devices to the connected_usb_devices list
            if new_ports:
                for port in new_ports:
                    if is_usb_midi_device(port) and port not in connected_usb_devices:
                        connected_usb_devices.append(port)
                        print(f"Added {port} to connected devices list. Current order: {connected_usb_devices}")
                
                # Check if new devices were plugged in while in manual mode
                if manual_mode:
                    usb_new_ports = [p for p in new_ports if is_usb_midi_device(p)]
                    if usb_new_ports:
                        print(f"New USB devices detected in manual mode, NOT auto-connecting: {usb_new_ports}")
                        # Do NOT perform auto connections in manual mode

            last_ports = current_ports
            cleanup_invalid_connections()

            # Only perform auto connections if not in manual mode
            if not manual_mode:
                perform_auto_connections()
            else:
                print("In manual mode - skipping auto connections")

    except Exception as e:
        print(f"Error updating port list: {e}")

def cleanup_auto_connections():
    """Disconnect all auto-connected devices"""
    try:
        current_inputs = set(filter_ports(mido.get_input_names()))
        current_outputs = set(filter_ports(mido.get_output_names()))
        to_remove = []
        for connection in auto_connections:
            from_port, to_port = connection
            if from_port not in current_inputs or to_port not in current_outputs:
                to_remove.append(connection)
        for connection in to_remove:
            auto_connections.discard(connection)
            connection_log.discard(connection)
            close_midi_connection(connection[0], connection[1])
            print(f"Auto-disconnected unplugged USB device connection: {connection[0]} -> {connection[1]}")
    except Exception as e:
        print(f"Error cleaning up auto connections: {e}")

def system_level_midi_reset():
    """Perform a system-level reset of MIDI devices"""
    print("PERFORMING SYSTEM-LEVEL MIDI RESET")
    
    # First close all our tracked connections
    close_all_midi_connections()
    
    # Clear all tracking data
    active_midi_connections.clear()
    midi_threads.clear()
    
    try:
        # Reload the mido module to reset its internal state
        importlib.reload(mido)
        
        # On Linux, we can use ALSA commands to reset MIDI
        if platform.system() == "Linux":
            try:
                # Stop ALSA sequencer
                subprocess.run(["sudo", "service", "alsa-utils", "stop"], check=False)
                time.sleep(0.5)
                # Restart ALSA sequencer
                subprocess.run(["sudo", "service", "alsa-utils", "start"], check=False)
                time.sleep(0.5)
            except Exception as e:
                print(f"Error resetting ALSA: {e}")
        
        # On macOS, we can use system_profiler to list MIDI devices
        elif platform.system() == "Darwin":
            try:
                subprocess.run(["killall", "CoreMIDI"], check=False)
                time.sleep(0.5)
            except Exception as e:
                print(f"Error resetting CoreMIDI: {e}")
        
        # On Windows, we can restart the MIDI service
        elif platform.system() == "Windows":
            try:
                subprocess.run(["net", "stop", "AudioSrv"], check=False)
                time.sleep(0.5)
                subprocess.run(["net", "start", "AudioSrv"], check=False)
                time.sleep(0.5)
            except Exception as e:
                print(f"Error resetting Windows Audio service: {e}")
        
        print("System-level MIDI reset completed")
    except Exception as e:
        print(f"Error during system-level MIDI reset: {e}")

def cleanup_invalid_connections():
    input_ports = set(filter_ports(mido.get_input_names()))
    output_ports = set(filter_ports(mido.get_output_names()))
    to_remove = []
    for from_port, to_port in list(connection_log):
        if from_port not in input_ports or to_port not in output_ports:
            to_remove.append((from_port, to_port))
    for connection in to_remove:
        connection_log.discard(connection)
        manual_connection_log.discard(connection)
        auto_connections.discard(connection)
        close_midi_connection(connection[0], connection[1])
        print(f"Removed invalid connection: {connection[0]} -> {connection[1]}")

def create_midi_connection(from_port_name, to_port_name):
    try:
        input_ports = mido.get_input_names()
        output_ports = mido.get_output_names()
        if from_port_name not in input_ports:
            print(f"Input port '{from_port_name}' not found")
            return False
        if to_port_name not in output_ports:
            print(f"Output port '{to_port_name}' not found")
            return False
        connection_key = (from_port_name, to_port_name)
        
        # If connection already exists, close it first to ensure clean state
        if connection_key in active_midi_connections:
            close_midi_connection(from_port_name, to_port_name)
            print(f"Closed existing connection before recreating: {from_port_name} -> {to_port_name}")
        
        input_port = mido.open_input(from_port_name)
        output_port = mido.open_output(to_port_name)

        # Send program change on channel 10 (zero-based channel 9)
        program_change_msg = mido.Message('program_change', program=0, channel=9)
        output_port.send(program_change_msg)

        active_midi_connections[connection_key] = {'input': input_port, 'output': output_port}
        thread = threading.Thread(target=midi_forwarder, args=(input_port, output_port, connection_key), daemon=True)
        thread.start()
        midi_threads[connection_key] = thread
        print(f"MIDI connection created: {from_port_name} -> {to_port_name}")
        return True
    except Exception as e:
        print(f"Error creating MIDI connection: {e}")
        return False

def midi_forwarder(input_port, output_port, connection_key):
    try:
        print(f"Starting MIDI forwarding for {connection_key}")
        for message in input_port:
            if connection_key not in active_midi_connections:
                break
            if hasattr(message, 'channel'):
                # Forward all messages forcing channel to 10 (zero-based 9)
                new_msg = message.copy(channel=9)
                output_port.send(new_msg)
                if new_msg.type in ['note_on', 'note_off']:
                    print(f"MIDI: Forwarded {new_msg.type} on channel 10 from {connection_key[0]} to {connection_key[1]}")
            else:
                output_port.send(message)
    except Exception as e:
        print(f"Error in MIDI forwarding for {connection_key}: {e}")
    finally:
        print(f"MIDI forwarding stopped for {connection_key}")

def close_midi_connection(from_port_name, to_port_name):
    connection_key = (from_port_name, to_port_name)
    try:
        if connection_key in active_midi_connections:
            connection = active_midi_connections[connection_key]
            del active_midi_connections[connection_key]
            if 'input' in connection and connection['input']:
                try:
                    connection['input'].close()
                    print(f"Closed input port: {from_port_name}")
                except Exception as e:
                    print(f"Error closing input port: {e}")
            if 'output' in connection and connection['output']:
                try:
                    connection['output'].close()
                    print(f"Closed output port: {to_port_name}")
                except Exception as e:
                    print(f"Error closing output port: {e}")
            if connection_key in midi_threads:
                del midi_threads[connection_key]
            print(f"MIDI connection fully closed: {from_port_name} -> {to_port_name}")
            return True
        else:
            print(f"Connection not found in active_midi_connections: {from_port_name} -> {to_port_name}")
            return False
    except Exception as e:
        print(f"Error in close_midi_connection: {e}")
        return False

def close_all_midi_connections():
    connections_to_close = list(active_midi_connections.keys())
    for from_port, to_port in connections_to_close:
        close_midi_connection(from_port, to_port)
    print("All MIDI connections closed")

def perform_auto_connections():
    global manual_mode, connected_usb_devices
    if manual_mode:
        # Manual mode disables auto-connect
        print("Manual mode is ON - skipping auto-connections")
        return
    try:
        current_inputs = filter_ports(mido.get_input_names())
        current_outputs = filter_ports(mido.get_output_names())

        # Use the connected_usb_devices list to determine connection order
        usb_devices = [device for device in connected_usb_devices if is_usb_midi_device(device)]
        
        # Filter to ensure devices are actually available
        available_usb_devices = [device for device in usb_devices 
                               if device in current_inputs or device in current_outputs]
        
        print(f"Available USB devices in order of connection: {available_usb_devices}")
        
        if len(available_usb_devices) < 2:
            print(f"Not enough USB devices for auto-connection: {len(available_usb_devices)} found")
            return

        # The first device in the list becomes the input, the second becomes the output
        input_port = available_usb_devices[0]
        output_port = available_usb_devices[1]
        
        # Verify these ports are actually available as input/output
        if input_port not in current_inputs:
            print(f"Selected input port {input_port} is not available as an input")
            return
            
        if output_port not in current_outputs:
            print(f"Selected output port {output_port} is not available as an output")
            return

        auto_connection_key = (input_port, output_port)
        if auto_connection_key in connection_log:
            print(f"Connection already exists: {input_port} -> {output_port}")
            return

        # Disconnect any existing auto-connections that conflict
        conflicts = [conn for conn in auto_connections if conn[0] == input_port or conn[1] == output_port]
        for conn in conflicts:
            auto_connections.discard(conn)
            connection_log.discard(conn)
            close_midi_connection(conn[0], conn[1])
            print(f"Disconnected conflicting auto-connection: {conn[0]} -> {conn[1]}")

        success = create_midi_connection(input_port, output_port)
        if success:
            auto_connections.add(auto_connection_key)
            connection_log.add(auto_connection_key)
            print(f"Auto-connected USB device: {input_port} -> {output_port}")
        else:
            print(f"Failed to auto-connect: {input_port} -> {output_port}")

    except Exception as e:
        print(f"Error during auto-connection: {e}")

def verify_connections_closed():
    """Verify that all MIDI connections are properly closed"""
    if active_midi_connections:
        print(f"WARNING: {len(active_midi_connections)} connections still active after attempted closure")
        return False
    return True

def switch_to_auto_mode():
    """Switch from manual mode to auto mode"""
    global manual_mode, connected_usb_devices
    
    if not manual_mode:
        return
    
    print("SWITCHING TO AUTO MODE")
    
    # First explicitly close all active connections
    connections_to_close = list(active_midi_connections.keys())
    for from_port, to_port in connections_to_close:
        close_midi_connection(from_port, to_port)
    
    # Small delay to ensure connections are fully terminated
    time.sleep(0.5)
    
    # Perform system-level MIDI reset
    system_level_midi_reset()
    
    # Clear all connection tracking
    connection_log.clear()
    manual_connection_log.clear()
    auto_connections.clear()
    
    # Set manual mode flag
    manual_mode = False
    
    # Verify connections are closed
    if not verify_connections_closed():
        print("WARNING: Some connections may still be active after switching to auto mode")
    
    # Re-establish auto connections
    perform_auto_connections()
    
    print("Switched to auto mode - all manual connections removed")

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    try:
        filtered_inputs = filter_ports(mido.get_input_names())
        filtered_outputs = filter_ports(mido.get_output_names())
        
        # In manual mode, show all connections
        # In auto mode, only show auto connections
        displayed_connections = list(connection_log) if manual_mode else list(auto_connections)
        
        return jsonify({
            'input_ports': filtered_inputs,
            'output_ports': filtered_outputs,
            'connections': displayed_connections,
            'auto_connections': list(auto_connections),
            'manual_connections': list(manual_connection_log),
            'manual_mode': manual_mode
        })
    except Exception as e:
        print(f"Error in status route: {e}")
        return jsonify({
            'input_ports': [],
            'output_ports': [],
            'connections': [],
            'auto_connections': [],
            'manual_connections': [],
            'manual_mode': manual_mode
        })

@app.route('/connect', methods=['POST'])
def connect():
    global manual_mode
    from_port = request.form.get('from')
    to_port = request.form.get('to')
    
    if not from_port or not to_port:
        return redirect(url_for('index', error='Please select both input and output ports'))
    if from_port == to_port:
        return redirect(url_for('index', error='Input and output ports cannot be the same'))
    
    # Only allow manual connections in manual mode
    if not manual_mode:
        return jsonify({"success": False, "message": "Manual connections are only allowed in manual mode"}), 400
    
    connection_tuple = (from_port, to_port)
    if connection_tuple in connection_log:
        return redirect(url_for('index', error='Connection already exists'))
    
    if create_midi_connection(from_port, to_port):
        connection_log.add(connection_tuple)
        manual_connection_log.add(connection_tuple)
        print(f"Manual connection created: {from_port} -> {to_port}")
        return redirect(url_for('index', connected='true'))
    else:
        return redirect(url_for('index', error='Failed to create MIDI connection - check that ports exist'))

@app.route('/disconnect', methods=['POST'])
def disconnect():
    try:
        from_port = request.form.get('from')
        to_port = request.form.get('to')
        if not from_port or not to_port:
            return jsonify({"success": False, "message": "Missing port information"}), 400
        
        connection_tuple = (from_port, to_port)
        if connection_tuple not in connection_log:
            return jsonify({"success": False, "message": "Connection not found"}), 404
        
        # In manual mode, allow disconnecting any connection
        # In auto mode, only allow disconnecting manual connections
        if not manual_mode and connection_tuple in auto_connections:
            return jsonify({"success": False, "message": "Cannot disconnect auto-connections in auto mode"}), 400
        
        success = close_midi_connection(from_port, to_port)
        connection_log.discard(connection_tuple)
        manual_connection_log.discard(connection_tuple)
        auto_connections.discard(connection_tuple)
        
        if success:
            print(f"Successfully disconnected: {from_port} -> {to_port}")
            return jsonify({"success": True, "message": "Connection disconnected successfully"})
        else:
            return jsonify({"success": True, "message": "Connection removed from tracking"})
    except Exception as e:
        print(f"Error in disconnect route: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

@app.route('/toggle_manual_mode', methods=['POST'])
def toggle_manual_mode():
    global manual_mode
    new_mode = request.json.get('manual_mode', False)
    
    # If toggling from auto to manual
    if new_mode and not manual_mode:
        print("TOGGLING TO MANUAL MODE - DISCONNECTING ALL CONNECTIONS")
        
        # First explicitly close all active connections
        connections_to_close = list(active_midi_connections.keys())
        for from_port, to_port in connections_to_close:
            close_midi_connection(from_port, to_port)
        
        # Small delay to ensure connections are fully terminated
        time.sleep(0.5)
        
        # Perform system-level MIDI reset
        system_level_midi_reset()
        
        # Additional delay after reset
        time.sleep(0.5)
        
        # Clear all connection tracking
        connection_log.clear()
        auto_connections.clear()
        manual_connection_log.clear()  # Also clear manual connections
        
        # Verify connections are closed
        if not verify_connections_closed():
            print("WARNING: Some connections may still be active after switching to manual mode")
            
            # Force close any remaining connections
            for key in list(active_midi_connections.keys()):
                try:
                    connection = active_midi_connections[key]
                    if 'input' in connection and connection['input']:
                        connection['input'].close()
                    if 'output' in connection and connection['output']:
                        connection['output'].close()
                    del active_midi_connections[key]
                    print(f"Force closed connection: {key}")
                except Exception as e:
                    print(f"Error force closing connection {key}: {e}")
        
        # Set manual mode flag
        manual_mode = True
        print("Switched to manual mode - all connections physically disconnected")
    
    # If toggling from manual to auto
    elif not new_mode and manual_mode:
        switch_to_auto_mode()
    
    return jsonify({"manual_mode": manual_mode})

def monitor_ports():
    global monitor_running
    while monitor_running:
        try:
            update_port_list()
        except Exception as e:
            print(f"Error monitoring ports: {e}")
        time.sleep(0.5)

if __name__ == '__main__':
    # Start the port monitor thread
    monitor_thread = threading.Thread(target=monitor_ports, daemon=True)
    monitor_thread.start()
    
    # Register cleanup function
    import atexit
    
    def cleanup():
        global monitor_running
        monitor_running = False
        close_all_midi_connections()
    
    atexit.register(cleanup)
    
    print("MIDI Router started with auto-connect and manual mode toggle.")
    app.run(debug=True, host='0.0.0.0', port=5050)

