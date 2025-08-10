// call.js
const wsUrl = "ws://localhost:5000/client";
let socket;
let callTimer;

// Get call_sid from URL
const urlParams = new URLSearchParams(window.location.search);
const callSid = urlParams.get('call_sid');

// Elements
const statusBadge = document.getElementById("statusBadge");
const reasoningEl = document.getElementById("reasoning");
const fraudAlert = document.getElementById("fraudAlert");
const alertReason = document.getElementById("alertReason");
const transcriptLog = document.getElementById("transcriptLog");
const riskLevel = document.getElementById("riskLevel");
const riskProgress = document.getElementById("riskProgress");
const callerNumber = document.getElementById("callerNumber");
const startTimeEl = document.getElementById("startTime");
const callTimerEl = document.getElementById("callTimer");
const callStatusIcon = document.getElementById("callStatusIcon");
const callStatusText = document.getElementById("callStatusText");

// Set start time
const startTime = new Date();
startTimeEl.textContent = startTime.toLocaleTimeString();

// Start call timer
let callSeconds = 0;
callTimer = setInterval(() => {
  callSeconds++;
  const minutes = Math.floor(callSeconds / 60);
  const seconds = callSeconds % 60;
  callTimerEl.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}, 1000);

function connect() {
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    statusBadge.textContent = "Live";
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-green-500";
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    // Only process events for this call
    if (data.call_sid !== callSid) return;
    
    if (data.event === "fraud_update") {
      processFraudUpdate(data);
    }
    else if (data.event === "call_ended") {
      endCall();
    }
  };

  socket.onclose = () => {
    statusBadge.textContent = "Disconnected";
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-gray-500";
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function processFraudUpdate(data) {
  reasoningEl.textContent = `${data.reasoning} [${data.confidence}]`;
  
  // Update risk indicator
  const riskMap = {
    "low": {text: "Low Risk", width: "30%", color: "text-green-600"},
    "medium": {text: "Medium Risk", width: "60%", color: "text-yellow-600"},
    "high": {text: "High Risk", width: "90%", color: "text-orange-600"}
  };
  
  const riskInfo = riskMap[data.confidence] || riskMap.medium;
  riskLevel.textContent = riskInfo.text;
  riskLevel.className = `font-medium ${riskInfo.color}`;
  riskProgress.style.width = riskInfo.width;
  
  // Update status
  if (data.is_fraudulent) {
    statusBadge.textContent = `FRAUD: ${data.fraud_type.toUpperCase()}`;
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-red-600";
    
    callStatusIcon.textContent = "🚨";
    callStatusText.textContent = "Fraud Detected!";
    callStatusText.className = "text-xl font-semibold text-red-600";
    
    alertReason.textContent = data.reasoning;
    fraudAlert.classList.remove("hidden");
  } else {
    statusBadge.textContent = "Safe";
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-green-500";
    fraudAlert.classList.add("hidden");
    
    callStatusIcon.textContent = "📞";
    callStatusText.textContent = "In Progress";
    callStatusText.className = "text-xl font-semibold";
  }
  
  // Add to transcript
  const p = document.createElement("p");
  p.innerHTML = `<span class="font-medium">[${new Date().toLocaleTimeString()}]</span> ${data.reasoning}`;
  p.className = "py-1 border-b border-gray-100";
  transcriptLog.prepend(p);
}

function endCall() {
  clearInterval(callTimer);
  statusBadge.textContent = "Call Ended";
  statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-gray-500";
  
  callStatusIcon.textContent = "📴";
  callStatusText.textContent = "Call Ended";
  callStatusText.className = "text-xl font-semibold text-gray-600";
  
  // Disable buttons after call ends
  document.querySelectorAll("button").forEach(btn => {
    btn.disabled = true;
    btn.classList.add("opacity-50", "cursor-not-allowed");
  });
}

// Initialize
connect();

// Simulate caller number for demo (replace with actual data)
callerNumber.textContent = "+1 (" + Math.floor(Math.random() * 900 + 100) + ") " + 
  Math.floor(Math.random() * 900 + 100) + "-" + Math.floor(Math.random() * 9000 + 1000);