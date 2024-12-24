function showModal(modalId, modalMsg) {
    var modal = document.getElementById(modalId)
    var modalBody = modal.getElementsByClassName('modal-title')[0]
    modalBody.innerHTML = modalMsg
    $(modal).modal('show')
}

function hideModal(modalId) {
    var modal = document.getElementById(modalId)
    $(modal).modal('hide')
}


document.addEventListener('DOMContentLoaded', function () {
    const flashMessages = document.querySelectorAll('#flash-messages .alert');
    flashMessages.forEach(function (message) {
        setTimeout(function () {
            message.style.display = 'none';
        }, 5000); // Adjust time (in milliseconds) as needed
    });
});