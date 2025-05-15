function showModal(modalId, modalMsg) {
    let modal = document.getElementById(modalId)
    let modalBody = modal.getElementsByClassName('modal-title')[0]
    modalBody.innerHTML = modalMsg
    $(modal).modal('show')
}

function hideModal(modalId) {
    let modal = document.getElementById(modalId)
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