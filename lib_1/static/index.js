const wsUrl = "ws://localhost:5000/client"; // Matches your Python server
let socket;

const statusBadge = document.getElementById("statusBadge");
const reasoningEl = document.getElementById("reasoning");
const fraudAlert = document.getElementById("fraudAlert");
const alertReason = document.getElementById("alertReason");
const transcriptLog = document.getElementById("transcriptLog");

document.getElementById("startTime").textContent = new Date().toLocaleTimeString();

function connect() {
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Connected to fraud detection backend");
    statusBadge.textContent = "Live";
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-green-500";
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event !== "fraud_update") return;

    reasoningEl.textContent = `${data.reasoning} [${data.confidence}]`;

    if (data.is_fraudulent) {
      const typeLabels = {
        content: "Suspicious Content",
        vocal: "Suspicious Voice",
        both: "High Risk (Content + Voice)"
      };
      const label = typeLabels[data.fraud_type] || "Suspicious";

      statusBadge.textContent = `FRAUD: ${label}`;
      statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-red-600";

      alertReason.textContent = data.reasoning;
      fraudAlert.classList.remove("hidden");

      // Optional: play alert sound
      // new Audio('/alert.mp3').play();
    } else {
      statusBadge.textContent = "Safe";
      statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-green-500";
      fraudAlert.classList.add("hidden");
    }

    // Optional: log to UI
    const p = document.createElement("p");
    p.textContent = `[${data.confidence}] ${data.reasoning}`;
    p.className = "mt-1";
    transcriptLog.appendChild(p);
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
  };

  socket.onclose = () => {
    console.log("Connection closed. Reconnecting...");
    statusBadge.textContent = "Disconnected";
    statusBadge.className = "px-3 py-1 rounded-full text-white text-sm bg-gray-500";
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

// Connect on load
connect();