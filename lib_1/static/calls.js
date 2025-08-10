// calls.js
const wsUrl = "ws://localhost:5000/client";
let socket;
const callsContainer = document.getElementById("callsContainer");
const emptyState = document.getElementById("emptyState");
const callCount = document.getElementById("callCount");
const connectionStatus = document.getElementById("connectionStatus");

// Track active calls
const activeCalls = new Map();

function connect() {
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Connected to backend");
    connectionStatus.innerHTML = `
      <span class="h-3 w-3 rounded-full bg-green-500 mr-2"></span>
      <span>Live</span>
    `;
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
      case "call_started":
        addCallCard(data);
        break;
        
      case "fraud_update":
        updateCallCard(data);
        break;
        
      case "call_ended":
        endCall(data.call_sid);
        break;
    }
    
    updateCallCount();
  };

  socket.onclose = () => {
    console.log("Connection closed. Reconnecting...");
    connectionStatus.innerHTML = `
      <span class="h-3 w-3 rounded-full bg-red-500 mr-2"></span>
      <span>Disconnected - Reconnecting...</span>
    `;
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function addCallCard(callData) {
  emptyState.classList.add("hidden");
  
  const callCard = document.createElement("div");
  callCard.className = "call-card status-connecting bg-white rounded-lg shadow overflow-hidden";
  callCard.id = `call-${callData.call_sid}`;
  callCard.innerHTML = `
    <div class="p-5">
      <div class="flex justify-between items-start">
        <div>
          <div class="flex items-center mb-2">
            <span class="status-indicator h-3 w-3 rounded-full bg-gray-500 mr-2"></span>
            <span class="status-text text-sm font-medium">Connecting...</span>
          </div>
          <h3 class="text-xl font-semibold">${callData.caller}</h3>
          <p class="text-gray-500 text-sm">${formatTime(callData.start_time)}</p>
        </div>
        <button class="view-call-btn p-2 text-blue-600 hover:bg-blue-50 rounded-full" 
                data-call-sid="${callData.call_sid}">
          <i class="fas fa-expand-alt"></i>
        </button>
      </div>
      
      <div class="mt-4">
        <div class="flex justify-between text-sm">
          <span>Risk Level:</span>
          <span class="risk-level font-medium">Analyzing...</span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2 mt-1">
          <div class="risk-bar h-2 rounded-full bg-gray-500" style="width: 0%"></div>
        </div>
      </div>
      
      <div class="mt-4 text-sm">
        <p class="update-text text-gray-600">Waiting for analysis...</p>
      </div>
    </div>
    
    <div class="bg-gray-50 px-5 py-3 text-xs text-gray-500 flex justify-between">
      <span>ID: ${callData.call_sid}</span>
      <span class="timer">00:00</span>
    </div>
  `;
  
  callsContainer.prepend(callCard);
  activeCalls.set(callData.call_sid, {
    element: callCard,
    startTime: new Date(callData.start_time),
    timer: setInterval(() => updateTimer(callData.call_sid), 1000)
  });
  
  // Add event listener to view button
  callCard.querySelector(".view-call-btn").addEventListener("click", () => {
    window.location.href = `call.html?call_sid=${callData.call_sid}`;
  });
}

function updateCallCard(data) {
  const callId = data.call_sid;
  if (!activeCalls.has(callId)) return;
  
  const callCard = activeCalls.get(callId).element;
  const statusIndicator = callCard.querySelector(".status-indicator");
  const statusText = callCard.querySelector(".status-text");
  const riskLevel = callCard.querySelector(".risk-level");
  const riskBar = callCard.querySelector(".risk-bar");
  const updateText = callCard.querySelector(".update-text");
  
  // Update status
  callCard.classList.remove("status-connecting", "status-active", "status-fraud");
  
  if (data.is_fraudulent) {
    callCard.classList.add("status-fraud");
    statusIndicator.className = "status-indicator h-3 w-3 rounded-full bg-red-500 mr-2 animate-pulse";
    statusText.textContent = "Fraud Detected!";
    statusText.className = "status-text text-sm font-medium text-red-600";
    riskLevel.textContent = "HIGH RISK";
    riskLevel.className = "risk-level font-medium text-red-600";
    riskBar.className = "risk-bar h-2 rounded-full bg-red-500";
    riskBar.style.width = "100%";
  } else {
    callCard.classList.add("status-active");
    statusIndicator.className = "status-indicator h-3 w-3 rounded-full bg-green-500 mr-2";
    statusText.textContent = "In Progress";
    statusText.className = "status-text text-sm font-medium text-green-600";
    
    // Calculate risk level
    const confidenceMap = {
      "low": {text: "Low Risk", width: "30%", color: "bg-green-400"},
      "medium": {text: "Medium Risk", width: "60%", color: "bg-yellow-400"},
      "high": {text: "High Risk", width: "90%", color: "bg-orange-400"}
    };
    
    const confidence = confidenceMap[data.confidence] || confidenceMap.medium;
    riskLevel.textContent = confidence.text;
    riskBar.className = `risk-bar h-2 rounded-full ${confidence.color}`;
    riskBar.style.width = confidence.width;
  }
  
  // Update reasoning
  updateText.textContent = data.reasoning;
}

function endCall(callSid) {
  if (!activeCalls.has(callSid)) return;
  
  const { element, timer } = activeCalls.get(callSid);
  clearInterval(timer);
  
  element.classList.remove("status-connecting", "status-active", "status-fraud");
  element.classList.add("status-ended");
  
  element.querySelector(".status-indicator").className = 
    "status-indicator h-3 w-3 rounded-full bg-gray-500 mr-2";
  element.querySelector(".status-text").textContent = "Call Ended";
  element.querySelector(".status-text").className = "status-text text-sm font-medium text-gray-600";
  
  // Remove after delay
  setTimeout(() => {
    element.remove();
    activeCalls.delete(callSid);
    updateCallCount();
    
    if (activeCalls.size === 0) {
      emptyState.classList.remove("hidden");
    }
  }, 5000);
}

function updateTimer(callSid) {
  if (!activeCalls.has(callSid)) return;
  
  const { element, startTime } = activeCalls.get(callSid);
  const timerEl = element.querySelector(".timer");
  
  const now = new Date();
  const diff = Math.floor((now - startTime) / 1000); // in seconds
  const minutes = Math.floor(diff / 60);
  const seconds = diff % 60;
  
  timerEl.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function updateCallCount() {
  callCount.textContent = activeCalls.size;
}

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Filter functionality
document.querySelectorAll(".filter-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    
    const filter = btn.dataset.filter;
    callsContainer.querySelectorAll(".call-card").forEach(card => {
      card.style.display = "block";
      
      if (filter === "active" && card.classList.contains("status-ended")) {
        card.style.display = "none";
      }
      else if (filter === "safe" && !card.classList.contains("status-active")) {
        card.style.display = "none";
      }
      else if (filter === "fraud" && !card.classList.contains("status-fraud")) {
        card.style.display = "none";
      }
    });
  });
});

// Initialize
connect();