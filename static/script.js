// Theme Toggle
const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;

// Check for saved theme preference or system preference
const savedTheme = localStorage.getItem('theme');
const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

if (savedTheme) {
    html.setAttribute('data-theme', savedTheme);
    themeToggle.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
} else if (systemDark) {
    html.setAttribute('data-theme', 'dark');
    themeToggle.textContent = '☀️';
}

themeToggle.addEventListener('click', () => {
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    themeToggle.textContent = newTheme === 'dark' ? '☀️' : '🌙';
});

document.getElementById('filterForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const generateBtn = document.getElementById('generateBtn');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const errorDiv = document.getElementById('error');

    // 1. Collect Data
    const tagsInput = document.getElementById('tags').value;
    const fandomInput = document.getElementById('fandom').value;

    // Get Checked Categories
    const categoryCheckboxes = document.querySelectorAll('input[name="category"]:checked');
    const categories = Array.from(categoryCheckboxes).map(cb => cb.value);

    // Parse tags (split by comma, trim whitespace, remove empty strings)
    const tags = tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0);

    // 2. Client Side Validation
    if (tags.length === 0 && !fandomInput && categories.length === 0) {
        showError("Please enter at least a tag, fandom, or relationship category.");
        return;
    }

    // 3. UI State: Loading
    generateBtn.disabled = true;
    loadingDiv.classList.remove('hidden');
    resultDiv.classList.add('hidden');
    errorDiv.classList.add('hidden');

    // Hide autocomplete and prevent it from reopening
    isSearching = true;
    clearTimeout(autocompleteTimeout);
    document.getElementById('autocompleteDropdown').classList.add('hidden');


    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tags: tags,
                categories: categories,
                fandom: fandomInput
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "An unknown error occurred");
        }



        // 5. Render Result
        document.getElementById('resTitle').textContent = data.title;
        document.getElementById('resAuthor').textContent = data.author;
        document.getElementById('resRating').textContent = data.rating;
        document.getElementById('resWords').textContent = data.word_count ? parseInt(data.word_count).toLocaleString() : "Unknown";
        document.getElementById('resLink').href = data.url;

        resultDiv.classList.remove('hidden');

    } catch (err) {
        showError(err.message);
    } finally {
        generateBtn.disabled = false;
        loadingDiv.classList.add('hidden');
        isSearching = false;  // Allow autocomplete again
    }
});

function showError(msg) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = msg;
    errorDiv.classList.remove('hidden');
}



// Autocomplete functionality
let autocompleteTimeout;
let currentFocus = -1;
let isSearching = false;  // Flag to prevent autocomplete during search

const fandomInput = document.getElementById('fandom');
const dropdown = document.getElementById('autocompleteDropdown');

fandomInput.addEventListener('input', function () {
    // Don't show autocomplete while a search is in progress
    if (isSearching) return;

    const term = this.value.trim();

    clearTimeout(autocompleteTimeout);

    if (term.length < 2) {
        dropdown.classList.add('hidden');
        return;
    }

    // Debounce: wait 150ms after user stops typing (faster response)
    autocompleteTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/autocomplete/fandom?term=${encodeURIComponent(term)}`);
            const suggestions = await response.json();

            if (suggestions.length > 0) {
                showSuggestions(suggestions);
            } else {
                dropdown.classList.add('hidden');
            }
        } catch (err) {
            console.error('Autocomplete error:', err);
            dropdown.classList.add('hidden');
        }
    }, 300);
});

function showSuggestions(suggestions) {
    dropdown.innerHTML = '';
    currentFocus = -1;

    suggestions.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'autocomplete-item';
        div.textContent = item.name;
        div.dataset.value = item.id;

        div.addEventListener('click', function () {
            fandomInput.value = this.dataset.value;
            dropdown.classList.add('hidden');
        });

        dropdown.appendChild(div);
    });

    dropdown.classList.remove('hidden');
}

// Keyboard navigation
fandomInput.addEventListener('keydown', function (e) {
    const items = dropdown.querySelectorAll('.autocomplete-item');

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        currentFocus++;
        if (currentFocus >= items.length) currentFocus = 0;
        setActive(items);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        currentFocus--;
        if (currentFocus < 0) currentFocus = items.length - 1;
        setActive(items);
    } else if (e.key === 'Enter') {
        if (currentFocus > -1 && items[currentFocus]) {
            e.preventDefault();
            items[currentFocus].click();
        }
    } else if (e.key === 'Escape') {
        dropdown.classList.add('hidden');
    }
});

function setActive(items) {
    items.forEach((item, index) => {
        if (index === currentFocus) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// Close dropdown when clicking outside
document.addEventListener('click', function (e) {
    if (e.target !== fandomInput && !dropdown.contains(e.target)) {
        dropdown.classList.add('hidden');
    }
});