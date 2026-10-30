#!/bin/bash
# Quick script to check what's using the NVIDIA GPU

echo "🔍 Checking GPU Usage"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if NVIDIA drivers are loaded
if ! lsmod | grep -q nvidia; then
    echo "✅ NVIDIA drivers are NOT loaded (GPU is disabled)"
    echo ""
    echo "💡 Discrete GPU is off; display may be on integrated or another GPU"
    echo "💡 Run 'performance' to re-enable NVIDIA GPU"
    exit 0
fi

echo "ℹ️  NVIDIA drivers are loaded"
echo ""

# Check nvidia-smi for active processes
if command -v nvidia-smi &> /dev/null; then
    echo "📊 GPU Processes (from nvidia-smi):"
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null | \
        while IFS=',' read -r pid name mem; do
            if [ -n "$pid" ]; then
                echo "   PID $pid: $name (using $mem)"
            fi
        done
    
    # Also check graphics processes
    nvidia-smi pmon -c 1 2>/dev/null | grep -v "^#" | grep -v "no processes" | tail -n +2 | \
        while read -r gpu pid type sm mem enc dec command; do
            if [ -n "$pid" ] && [ "$pid" != "-" ]; then
                echo "   PID $pid: $command"
            fi
        done
    
    echo ""
fi

# Check which processes have /dev/nvidia* open
echo "📂 Processes with /dev/nvidia* open:"
if command -v fuser &> /dev/null; then
    for dev in /dev/nvidia*; do
        if [ -c "$dev" ] || [ -e "$dev" ]; then
            procs=$(sudo fuser "$dev" 2>/dev/null)
            if [ -n "$procs" ]; then
                echo "   $dev: PIDs $procs"
                for pid in $procs; do
                    if [ -d "/proc/$pid" ]; then
                        cmd=$(ps -p "$pid" -o comm= 2>/dev/null)
                        echo "      └─ $pid: $cmd"
                    fi
                done
            fi
        fi
    done
else
    echo "   ⚠ 'fuser' command not found, install with: sudo apt install psmisc"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 Close GPU apps before unloading drivers or changing power limits."
