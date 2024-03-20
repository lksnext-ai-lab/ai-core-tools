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