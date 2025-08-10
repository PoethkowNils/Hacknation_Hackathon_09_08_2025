$(document).ready(function () {
    //////////////          DIAL MODAL         ///////////////////////////////


    let btnOpenNumberPad = document.getElementById('btnOpenNumberPad')
    let inputPhoneNumber = document.getElementById('phoneNumber')
    let btnDelete = document.getElementById('btnDelete')


    btnOpenNumberPad.addEventListener('click', (event) => {
        $('#modal-dial').modal('show')
    })


    $('#btnCloseDialModal').bind('click', function () {
        $('#modal-dial').modal('hide')
    });

    $('.btnNumber').bind('click', function () {
        let text = $(this).text()
        inputPhoneNumber.value += text
    });


    btnDelete.addEventListener('click', (event) => {
        console.log('clicked', event)
        var str = inputPhoneNumber.value
        var position = inputPhoneNumber.selectionStart - 1;

        str = str.substr(0, position) + '' + str.substr(position + 1);
        inputPhoneNumber.value = str
    })


   ///////////////       CALL IN PROGRESS MODAL          ////////////////////////////
    $("#modal-call-in-progress").on('shown.bs.modal', function () {
        showCallDuration();
        // Reset fraud alert indicator when call starts
        $('#fraud-alert-indicator').addClass('d-none');
    });


    function showCallDuration() {
        let output = document.getElementById('callDuration');
        let ms = 0;
        let sec = 0;
        let min = 0;

        function timer() {
            ms++;
            if (ms >= 100) {
                sec++
                ms = 0
            }
            if (sec === 60) {
                min++
                sec = 0
            }
            if (min === 60) {
                ms,
                    sec,
                    min = 0;
            }

            let milli = ms < 10 ? `0` + ms : ms;
            let seconds = sec < 10 ? `0` + sec : sec;
            let minute = min < 10 ? `0` + min : min;

            let timer = `${minute}:${seconds}`;
            output.innerHTML = timer;
        };

        //Start timer
        function start() {
            time = setInterval(timer, 10);
        }

        //stop timer
        function stop() {
            clearInterval(time)
        }
        
        //reset timer
        function reset() {
            ms = 0;
            sec = 0;
            min = 0;

            output.innerHTML = `00:00:00`
        }

        // start the timer
        start()

        $("#modal-call-in-progress").on('hidden.bs.modal', function () {
            stop()
        });

    // Global function to update fraud alert in call modal
    window.updateFraudAlert = function(alert) {
        if (alert.is_fraudulent) {
            $('#fraud-alert-indicator').removeClass('d-none');
            $('#fraud-alert-text').html(`
                ${alert.reasoning}<br>
                <span class="badge bg-danger">${alert.fraud_type.toUpperCase()}</span>
                <span class="badge bg-warning">${alert.confidence.toUpperCase()}</span>
            `);
            
            // Flash the alert
            $('#fraud-alert-indicator').fadeTo(200, 0.3).fadeTo(200, 1.0);
        }
    };

    }

});
