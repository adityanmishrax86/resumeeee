(() => {
    const NOISE_LINES = [
        "apply now",
        "save job",
        "share job",
        "cookie settings",
        "privacy policy",
        "back to search"
    ];

    const REQUIREMENT_HEADINGS = [
        "requirements",
        "qualifications",
        "what you bring",
        "what we're looking for"
    ];

    const RESPONSIBILITY_HEADINGS = [
        "responsibilities",
        "what you'll do",
        "what you will do",
        "about the role"
    ];

    const KEYWORD_BOOSTS = [
        "responsibilities",
        "requirements",
        "qualifications",
        "experience",
        "benefits",
        "about the role",
        "what you'll do",
        "what we offer"
    ];

    function clean(text) {
        return (text || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
    }

    function cleanMultiline(text) {
        const value = (text || "").replace(/\u00a0/g, " ");
        const lines = value
            .split(/\r?\n/)
            .map((line) => clean(line))
            .filter(Boolean)
            .filter((line) => !NOISE_LINES.includes(line.toLowerCase()));
        return lines.join("\n").trim();
    }

    function getText(selectors, root = document) {
        for (const selector of selectors) {
            const node = root.querySelector(selector);
            const value = clean(node?.textContent || node?.innerText);
            if (value) {
                return value;
            }
        }
        return "";
    }

    function textFromNode(node) {
        if (!node) {
            return "";
        }
        return cleanMultiline(node.innerText || node.textContent || "");
    }

    function detectATS() {
        const host = location.hostname.toLowerCase();

        if (host.includes("greenhouse")) return "greenhouse";
        if (host.includes("lever.co")) return "lever";
        if (host.includes("myworkdayjobs")) return "workday";
        if (host.includes("taleo.net")) return "taleo";
        if (host.includes("oraclecloud")) return "oracle_hcm";
        if (host.includes("icims")) return "icims";
        if (host.includes("ashbyhq")) return "ashby";
        if (host.includes("smartrecruiters")) return "smartrecruiters";
        if (host.includes("successfactors")) return "sap_successfactors";

        return "generic";
    }

    function createBase(ats) {
        return {
            ats,
            company: "",
            role: "",
            location: "",
            description: "",
            requirements: "",
            responsibilities: "",
            url: window.location.href
        };
    }

    function mergeData(base, candidate) {
        const result = { ...base };
        const source = candidate || {};
        const keys = Object.keys(result);
        for (const key of keys) {
            const next = typeof source[key] === "string" ? source[key].trim() : "";
            if (next && !result[key]) {
                result[key] = next;
            }
        }
        for (const [key, value] of Object.entries(source)) {
            if (!(key in result) && value !== undefined) {
                result[key] = value;
            }
        }
        return result;
    }

    function splitSections(text) {
        const lines = (text || "").split(/\r?\n/).map((x) => clean(x)).filter(Boolean);
        let active = "";
        const req = [];
        const resp = [];

        lines.forEach((line) => {
            const lower = line.toLowerCase();
            if (REQUIREMENT_HEADINGS.some((h) => lower.includes(h))) {
                active = "requirements";
                return;
            }
            if (RESPONSIBILITY_HEADINGS.some((h) => lower.includes(h))) {
                active = "responsibilities";
                return;
            }
            if (active === "requirements") {
                req.push(line);
            }
            if (active === "responsibilities") {
                resp.push(line);
            }
        });

        return {
            requirements: req.join("\n").trim(),
            responsibilities: resp.join("\n").trim()
        };
    }

    function extractJsonLdJobPosting() {
        const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
        const candidates = [];

        function addNodes(value) {
            if (!value) {
                return;
            }
            if (Array.isArray(value)) {
                value.forEach(addNodes);
                return;
            }
            if (typeof value !== "object") {
                return;
            }
            if (Array.isArray(value["@graph"])) {
                value["@graph"].forEach(addNodes);
            }
            const type = value["@type"];
            const typeValue = Array.isArray(type) ? type.join(" ") : String(type || "");
            if (typeValue.toLowerCase().includes("jobposting")) {
                candidates.push(value);
            }
        }

        scripts.forEach((script) => {
            const raw = script.textContent || "";
            if (!raw.trim()) {
                return;
            }
            try {
                addNodes(JSON.parse(raw));
            } catch {
                // Ignore malformed JSON-LD blobs.
            }
        });

        if (!candidates.length) {
            return {};
        }

        const job = candidates[0];
        const company = clean(job?.hiringOrganization?.name);
        const role = clean(job?.title);

        let location = "";
        const rawLocation = job?.jobLocation;
        if (Array.isArray(rawLocation) && rawLocation.length) {
            const addr = rawLocation[0]?.address || rawLocation[0];
            location = clean([addr?.addressLocality, addr?.addressRegion, addr?.addressCountry].filter(Boolean).join(", "));
        } else if (rawLocation) {
            const addr = rawLocation?.address || rawLocation;
            location = clean([addr?.addressLocality, addr?.addressRegion, addr?.addressCountry].filter(Boolean).join(", "));
        }

        const description = cleanMultiline(job?.description || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities,
            datePosted: clean(job?.datePosted),
            employmentType: clean(Array.isArray(job?.employmentType) ? job?.employmentType.join(", ") : job?.employmentType),
            identifier: clean(typeof job?.identifier === "object" ? job?.identifier?.value : job?.identifier),
            originalTitle: role
        };
    }

    function findLargestContentBlock() {
        const blocks = Array.from(document.querySelectorAll("main, article, section, div"));
        const scored = blocks
            .map((node) => {
                const text = textFromNode(node);
                if (text.length < 500) {
                    return null;
                }
                const lower = text.toLowerCase();
                let score = text.length;
                KEYWORD_BOOSTS.forEach((keyword) => {
                    if (lower.includes(keyword)) {
                        score += 100;
                    }
                });
                return { node, text, score };
            })
            .filter(Boolean)
            .sort((a, b) => b.score - a.score);

        return scored[0] || null;
    }

    function extractGenericSemantic() {
        const role = getText(["h1"]);
        const company = getText([
            "[data-company-name]",
            ".company-name",
            ".posting-categories .sort-by-time.posting-category",
            "[class*='company']"
        ]);
        const location = getText([
            "[data-location]",
            ".location",
            "[class*='location']"
        ]);

        const semanticNode =
            document.querySelector("main") ||
            document.querySelector("article") ||
            document.querySelector("section");

        const semanticText = textFromNode(semanticNode);
        const largest = findLargestContentBlock();
        const description = semanticText || largest?.text || cleanMultiline(document.body?.innerText || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractGreenhouse() {
        const role = getText(["h1"]);
        const company = getText([".meta", ".company-name"]);
        const descNode = document.querySelector("#content");
        const description = textFromNode(descNode) || cleanMultiline(document.body?.innerText || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractLever() {
        const role = getText([".posting-headline h2", "h1"]);
        const company = clean(window.location.hostname.split(".")[0]);
        const location = getText([".posting-categories .sort-by-location", "[class*='location']"]);
        const sectionsRaw = Array.from(document.querySelectorAll(".section-wrapper")).map((el) => textFromNode(el)).filter(Boolean);
        const description = sectionsRaw.join("\n\n") || cleanMultiline(document.body?.innerText || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function waitForSettledDom(ms = 3000) {
        return new Promise((resolve) => {
            let timeoutId = null;
            const observer = new MutationObserver(() => {
                if (timeoutId) {
                    clearTimeout(timeoutId);
                }
                timeoutId = setTimeout(done, 400);
            });

            function done() {
                observer.disconnect();
                if (timeoutId) {
                    clearTimeout(timeoutId);
                }
                resolve();
            }

            observer.observe(document.body || document.documentElement, {
                childList: true,
                subtree: true,
                characterData: true
            });

            setTimeout(done, ms);
        });
    }

    function extractWorkday() {
        const role = getText(["h1"]);
        const location = getText(["[data-automation-id='locations']", "[class*='location']"]);
        const company = clean(window.location.hostname.split(".")[0]);

        const headings = Array.from(document.querySelectorAll("h2, h3, strong"));
        const headingTokens = ["job description", "responsibilities", "qualifications", "requirements", "about us"];
        let description = "";

        for (const heading of headings) {
            const headingText = clean(heading.textContent).toLowerCase();
            if (headingTokens.some((token) => headingText.includes(token))) {
                const parent = heading.closest("section, div, article") || heading.parentElement;
                description = textFromNode(parent);
                if (description.length > 200) {
                    break;
                }
            }
        }

        if (!description) {
            const candidates = Array.from(document.querySelectorAll("div"));
            const best = candidates
                .filter((el) => clean(el.innerText).length > 500)
                .sort((a, b) => clean(b.innerText).length - clean(a.innerText).length)[0];
            description = textFromNode(best);
        }

        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractTaleo() {
        const role = getText(["h1", "h2"]);
        const company = clean(window.location.hostname.split(".")[0]);
        const candidates = Array.from(document.querySelectorAll("table, div, span"));
        const description = candidates
            .map((el) => textFromNode(el))
            .filter((text) => {
                const lower = text.toLowerCase();
                return lower.includes("job description") || lower.includes("responsibilities") || lower.includes("qualifications");
            })
            .sort((a, b) => b.length - a.length)[0] || "";
        const sections = splitSections(description);

        return {
            company,
            role,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function safeStringify(value) {
        try {
            return JSON.stringify(value);
        } catch {
            return "";
        }
    }

    function extractOracleHcm() {
        const role = getText(["h1"]);
        const company = clean(window.location.hostname.split(".")[0]);
        let description = "";
        let location = "";
        let requisitionId = "";

        const scripts = Array.from(document.querySelectorAll("script"));
        for (const script of scripts) {
            const raw = script.textContent || "";
            if (!/(job|career|requisition|posting)/i.test(raw)) {
                continue;
            }
            const normalized = cleanMultiline(raw);
            if (normalized.length > description.length) {
                description = normalized;
            }
        }

        Object.keys(window).forEach((key) => {
            if (/(job|career|requisition|posting)/i.test(key)) {
                const value = window[key];
                const asText = cleanMultiline(safeStringify(value));
                if (asText.length > description.length) {
                    description = asText;
                }
                if (!location && value && typeof value === "object") {
                    location = clean(value.location || value.jobLocation || value.city);
                }
                if (!requisitionId && value && typeof value === "object") {
                    requisitionId = clean(value.requisitionId || value.reqId || value.id);
                }
            }
        });

        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities,
            identifier: requisitionId
        };
    }

    function extractIcims() {
        const role = getText(["h1"]);
        const company = getText(["[class*='company']"]) || clean(window.location.hostname.split(".")[0]);
        const descriptionNode =
            document.querySelector("article") ||
            document.querySelector("main") ||
            document.querySelector("[data-job-id]");
        const description = textFromNode(descriptionNode) || cleanMultiline(document.body?.innerText || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractAshby() {
        const role = getText(["h1"]);
        const company = getText(["[class*='company']"]) || clean(window.location.hostname.split(".")[0]);
        const mainNode = document.querySelector("main") || document.querySelector("article");
        const description = textFromNode(mainNode) || cleanMultiline(document.body?.innerText || "");
        const sections = splitSections(description);

        return {
            company,
            role,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractSmartRecruiters() {
        const role = getText(["h1"]);
        const company = getText(["[class*='company']"]) || clean(window.location.hostname.split(".")[0]);
        const mainNode =
            document.querySelector("[role='main']") ||
            document.querySelector("article") ||
            document.querySelector("main");
        const description = textFromNode(mainNode) || cleanMultiline(document.body?.innerText || "");
        const location = getText(["[class*='location']", "[data-testid*='location']"]);
        const sections = splitSections(description);

        return {
            company,
            role,
            location,
            description,
            requirements: sections.requirements,
            responsibilities: sections.responsibilities
        };
    }

    function extractSuccessFactors() {
        const role = getText(["h1"]);
        const company = clean(window.location.hostname.split(".")[0]);
        const semantic = extractGenericSemantic();
        return {
            company: semantic.company || company,
            role: semantic.role || role,
            location: semantic.location,
            description: semantic.description,
            requirements: semantic.requirements,
            responsibilities: semantic.responsibilities
        };
    }

    async function extractByAts(ats) {
        switch (ats) {
            case "greenhouse":
                return extractGreenhouse();
            case "lever":
                return extractLever();
            case "workday":
                await waitForSettledDom(3000);
                return extractWorkday();
            case "taleo":
                return extractTaleo();
            case "oracle_hcm":
                return extractOracleHcm();
            case "icims":
                return extractIcims();
            case "ashby":
                return extractAshby();
            case "smartrecruiters":
                return extractSmartRecruiters();
            case "sap_successfactors":
                return extractSuccessFactors();
            default:
                return {};
        }
    }

    async function runAtsPipeline() {
        const ats = detectATS();
        let data = createBase(ats);

        const jsonLd = extractJsonLdJobPosting();
        data = mergeData(data, jsonLd);

        const atsData = await extractByAts(ats);
        data = mergeData(data, atsData);

        const semantic = extractGenericSemantic();
        data = mergeData(data, semantic);

        const largest = findLargestContentBlock();
        if (largest && !data.description) {
            data.description = largest.text;
            const sections = splitSections(largest.text);
            if (!data.requirements) {
                data.requirements = sections.requirements;
            }
            if (!data.responsibilities) {
                data.responsibilities = sections.responsibilities;
            }
        }

        if (!data.description) {
            const bodyText = cleanMultiline(document.body?.innerText || "");
            data.description = bodyText;
            const sections = splitSections(bodyText);
            if (!data.requirements) {
                data.requirements = sections.requirements;
            }
            if (!data.responsibilities) {
                data.responsibilities = sections.responsibilities;
            }
        }

        return data;
    }

    window.__ATS_EXTRACTORS__ = {
        detectATS,
        runAtsPipeline,
        extractJsonLdJobPosting
    };
})();
