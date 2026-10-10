// SPDX-License-Identifier: EUPL-1.2
const screenshotDialog = document.getElementById('screenshot-dialog');
document.querySelector('.screenshot-link').addEventListener('click', event => {
  event.preventDefault();
  screenshotDialog.showModal();
});
