// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});

// Confirm delete actions
document.querySelectorAll('form[onsubmit]').forEach(form => {
    form.addEventListener('submit', function(e) {
        if (!confirm(this.getAttribute('onsubmit').replace('return confirm(', '').replace(')', ''))) {
            e.preventDefault();
        }
    });
});

// Search functionality
const searchInputs = document.querySelectorAll('.search-box input');
searchInputs.forEach(input => {
    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            window.location.href = '?search=' + encodeURIComponent(this.value);
        }
    });
});