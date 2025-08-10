$(function () {
    var device;
    var fraudSocket;  // WebSocket connection for fraud alerts
    var callActive = false; // Track if call is active

    log("Requesting Access Token...");
    // Using a relative link to access the Voice Token function
    $.getJSON("./token")
        .then(function (data) {
            log("Got a token.");
            console.log("Token: " + data.token);

            // Initialize WebSocket connection for fraud alerts
            const host = window.location.hostname;
            fraudSocket = new WebSocket(`ws://${host}:5000/client`);
            
            fraudSocket.onopen = function() {
                log("Connected to fraud detection service");
            };
            
            fraudSocket.onerror = function(err) {
                log("Fraud socket error: " + err.message);
            };
            
            fraudSocket.onclose = function() {
                log("Fraud socket connection closed");
            };
            
            fraudSocket.onmessage = function(event) {
                const alert = JSON.parse(event.data);
                log("Received fraud alert: " + alert.reasoning);
                
                // Update fraud panel (from home.html)
                if (typeof displayFraudAlert === 'function') {
                    displayFraudAlert(alert);
                }
                
                // Update call modal
                if (typeof updateFraudAlert === 'function') {
                    updateFraudAlert(alert);
                }
                
                // Play alert sound for high confidence fraud
                if (alert.is_fraudulent && alert.confidence === 'high') {
                    playAlertSound();
                }
            };

            // Setup Twilio.Device
            device = new Twilio.Device(data.token, {
                // Set Opus as our preferred codec. Opus generally performs better, requiring less bandwidth and
                // providing better audio quality in restrained network conditions. Opus will be default in 2.0.
                codecPreferences: ["opus", "pcmu"],
                // Use fake DTMF tones client-side. Real tones are still sent to the other end of the call,
                // but the client-side DTMF tones are fake. This prevents the local mic capturing the DTMF tone
                // a second time and sending the tone twice. This will be default in 2.0.
                fakeLocalDTMF: true,
                // Use `enableRingingState` to enable the device to emit the `ringing`
                // state. The TwiML backend also needs to have the attribute
                // `answerOnBridge` also set to true in the `Dial` verb. This option
                // changes the behavior of the SDK to consider a call `ringing` starting
                // from the connection to the TwiML backend to when the recipient of
                // the `Dial` verb answers.
                enableRingingState: true,
                debug: true,
            });

            device.on("ready", function (device) {
                log("Twilio.Device Ready!");
            });

            device.on("error", function (error) {
                log("Twilio.Device Error: " + error.message);
            });

            device.on("connect", function (conn) {
                log('Successfully established call!');
                callActive = true;
                $('#modal-call-in-progress').modal('show');
                
                // Notify fraud detection service that call started
                if (fraudSocket.readyState === WebSocket.OPEN) {
                    fraudSocket.send(JSON.stringify({
                        action: "call_started",
                        call_sid: conn.parameters.CallSid
                    }));
                }
            });

            device.on("disconnect", function (conn) {
                log("Call ended.");
                callActive = false;
                $('.modal').modal('hide');
                
                // Notify fraud detection service that call ended
                if (fraudSocket && fraudSocket.readyState === WebSocket.OPEN) {
                    fraudSocket.send(JSON.stringify({
                        action: "call_ended"
                    }));
                }
            });

            device.on("incoming", function (conn) {
                console.log(conn.parameters)
                log("Incoming connection from " + conn.parameters.From);
                $("#callerNumber").text(conn.parameters.From)
                $("#txtPhoneNumber").text(conn.parameters.From)

                $('#modal-incomming-call').modal('show')

                $('.btnReject').bind('click', function () {
                    $('.modal').modal('hide')
                    log("Rejected call ...");
                    conn.reject();
                })

                $('.btnAcceptCall').bind('click', function () {
                    $('.modal').modal('hide')
                    log("Accepted call ...");
                    conn.accept();
                })
            });
        })
        .catch(function (err) {
            console.log(err);
            log("Could not get a token from server!");
        });

    // Bind button to make call
    $('#btnDial').bind('click', function () {
        $('#modal-dial').modal('hide')

        // get the phone number to connect the call to
        var params = {
            To: document.getElementById("phoneNumber").value
        };

        // output destination number
        $("#txtPhoneNumber").text(params.To)
        
        // Clear previous alerts
        if (typeof clearFraudAlerts === 'function') {
            clearFraudAlerts();
        }

        console.log("Calling " + params.To + "...");
        if (device) {
            var outgoingConnection = device.connect(params);
            outgoingConnection.on("ringing", function () {
                log("Ringing...");
            });
        }
    })

    // Bind button to hangup call
    $('.btnHangUp').bind('click', function () {
        $('.modal').modal('hide')
        log("Hanging up...");
        if (device) {
            device.disconnectAll();
        }
    })

    // Activity log
    function log(message) {
        var logDiv = document.getElementById("log");
        logDiv.innerHTML += "<p>&gt;&nbsp;" + message + "</p>";
        logDiv.scrollTop = logDiv.scrollHeight;
    }

    // Play alert sound for fraud detection
    function playAlertSound() {
        // Only play if call is active
        if (!callActive) return;
        
        try {
            // Create audio context if not exists
            window.alertAudioContext = window.alertAudioContext || new (window.AudioContext || window.webkitAudioContext)();
            
            // Only play if not muted
            if (window.alertAudioContext.state !== 'suspended') {
                const oscillator = window.alertAudioContext.createOscillator();
                const gainNode = window.alertAudioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(window.alertAudioContext.destination);
                
                oscillator.type = 'sine';
                oscillator.frequency.setValueAtTime(880, window.alertAudioContext.currentTime);
                oscillator.frequency.setValueAtTime(440, window.alertAudioContext.currentTime + 0.1);
                
                gainNode.gain.setValueAtTime(0.3, window.alertAudioContext.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, window.alertAudioContext.currentTime + 0.3);
                
                oscillator.start();
                oscillator.stop(window.alertAudioContext.currentTime + 0.3);
            }
        } catch (e) {
            console.error("Error playing alert sound:", e);
        }
    }
    
    // Handle page visibility changes to manage audio context
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            if (window.alertAudioContext && window.alertAudioContext.state === 'suspended') {
                window.alertAudioContext.resume();
            }
        }
    });
});