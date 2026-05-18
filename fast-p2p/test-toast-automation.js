// Automation script to test Toast notifications
// Run this in the browser console at http://localhost:5174

async function testToastNotification() {
    console.log('Starting Toast notification test...');
    
    // Step 1: Click create button
    const createBtn = document.querySelector('.action-button-primary');
    if (!createBtn) {
        console.error('Create button not found!');
        return;
    }
    
    console.log('Clicking create button...');
    createBtn.click();
    
    // Wait for room to be created
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Step 2: Click copy link button
    const copyButtons = document.querySelectorAll('.text-button');
    const copyLinkBtn = Array.from(copyButtons).find(btn => btn.textContent.includes('copy link'));
    
    if (!copyLinkBtn) {
        console.error('Copy link button not found!');
        return;
    }
    
    if (copyLinkBtn.disabled) {
        console.error('Copy link button is disabled!');
        return;
    }
    
    console.log('Clicking copy link button...');
    copyLinkBtn.click();
    
    // Wait a moment for toast to appear
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Check if toast appeared
    const toastContainer = document.querySelector('.toast-container');
    const toast = document.querySelector('.toast');
    
    if (toastContainer && toast) {
        console.log('✅ SUCCESS! Toast notification appeared!');
        console.log('Toast message:', toast.querySelector('.toast-message')?.textContent);
        console.log('Toast type:', toast.className);
    } else {
        console.error('❌ FAILED! Toast notification did not appear!');
    }
}

// Run the test
testToastNotification();
