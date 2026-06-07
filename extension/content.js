(() => {
    function clean(text) {
        return (text || "").replace(/\s+/g, " ").trim();
    }

    function getText(selectors) {
        for (const selector of selectors) {
            const node = document.querySelector(selector);
            if (node && node.textContent) {
                const value = clean(node.textContent);
                if (value) {
                    return value;
                }
            }
        }
        return "";
    }

    function getAllItems(selectors) {
        let results = [];
        for (const selector of selectors) {
            const nodes = document.querySelectorAll(selector);
            if (nodes.length >= 1) {
                nodes.forEach(x => {
                    if (x && x.textContent)
                        results.push(clean(x.textContent));
                });
            }
        }
        return results;
    }

    function uniqueNonEmpty(items) {
        return [...new Set((items || []).map((x) => clean(x)).filter(Boolean))];
    }

    function wait(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function getDescription() {
        const descriptionContainer =
            document.querySelector("#job-details") ||
            document.querySelector(".jobs-description") ||
            document.querySelector(".jobs-box__html-content") ||
            document.querySelector("[data-job-detail-container]");

        if (!descriptionContainer) {
            return "";
        }

        return clean(descriptionContainer.innerText || descriptionContainer.textContent);
    }

    function stripHtml(html) {
        if (!html) {
            return "";
        }
        const temp = document.createElement("div");
        temp.innerHTML = html;
        return clean(temp.innerText || temp.textContent);
    }

    function parseLinkedInJobPostingJsonLd() {
        const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));

        for (const script of scripts) {
            const raw = script.textContent;
            if (!raw) {
                continue;
            }

            try {
                const parsed = JSON.parse(raw);
                const list = Array.isArray(parsed) ? parsed : [parsed];

                for (const item of list) {
                    const type = item?.["@type"];
                    if (type === "JobPosting") {
                        const locationAddress = item?.jobLocation?.address;
                        const locationText = [
                            locationAddress?.addressLocality,
                            locationAddress?.addressRegion,
                            locationAddress?.addressCountry
                        ].filter(Boolean).join(", ");

                        return {
                            title: clean(item?.title),
                            company: clean(item?.hiringOrganization?.name),
                            location: clean(locationText),
                            description: stripHtml(item?.description),
                            metadata: [
                                clean(item?.employmentType),
                                clean(item?.datePosted),
                                clean(item?.validThrough)
                            ].filter(Boolean)
                        };
                    }
                }
            } catch {
                // Ignore malformed ld+json blocks.
            }
        }

        return null;
    }

    function firstByClassContains(token, root = document) {
        return root.querySelector('[class*="' + token + '"]');
    }

    function allByClassContains(token, root = document) {
        return Array.from(root.querySelectorAll('[class*="' + token + '"]'));
    }

    function textsFromChildAnchors(parentClassToken) {
        const parent = firstByClassContains(parentClassToken);
        if (!parent) {
            return [];
        }
        const values = Array.from(parent.querySelectorAll("a"))
            .map((a) => clean(a.textContent))
            .filter(Boolean);
        return [...new Set(values)];
    }

    function extractNaukriJobDetails() {
        const expContainer = firstByClassContains("styles_jhc__exp");
        const experience = clean(expContainer?.querySelector("span")?.textContent);

        const companyContainer = firstByClassContains("styles_jd-header-comp-name");
        const companyName =
            clean(companyContainer?.querySelector("a")?.textContent) ||
            clean(companyContainer?.textContent);

        const roleTitle = clean(firstByClassContains("styles_jd-header-title")?.textContent);
        const salaryRange = clean(firstByClassContains("styles_jhc__salary")?.textContent);
        const locations = textsFromChildAnchors("styles_jhc__location");

        const descriptionContainer = firstByClassContains("styles_JDC__dang-inner-html");
        const jobDescription = clean(descriptionContainer?.innerText || descriptionContainer?.textContent);

        const keySkillContainers = allByClassContains("styles_key-skill");
        const keySkills = [
            ...new Set(
                keySkillContainers
                    .flatMap((container) => Array.from(container.querySelectorAll("a")))
                    .map((a) => clean(a.textContent))
                    .filter(Boolean)
            )
        ];

        return {
            source: "naukri",
            extractedAt: new Date().toISOString(),
            url: window.location.href,
            experience,
            companyName,
            roleTitle,
            salaryRange,
            locations,
            jobDescription,
            keySkills
        };
    }

    function extractLinkedInJobDetails() {
        const jsonLd = parseLinkedInJobPostingJsonLd();

        const title = jsonLd?.title || getText([
            ".job-details-jobs-unified-top-card__job-title h1",
            ".job-details-jobs-unified-top-card__job-title",
            ".t-24.t-bold.inline",
            "h1",
            "main h1",
            "[role='main'] h1"
        ]);

        const company = jsonLd?.company || getText([
            ".job-details-jobs-unified-top-card__company-name a",
            ".job-details-jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__primary-description a",
            ".jobs-unified-top-card__company-name",
            "a[href*='/company/']",
            "main a[href*='/company/']",
            "[role='main'] a[href*='/company/']"
        ]);

        const location = jsonLd?.location || getText([
            ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
            ".job-details-jobs-unified-top-card__bullet",
            ".jobs-unified-top-card__bullet",
            "main [aria-label*='location' i]",
            "[role='main'] [aria-label*='location' i]",
            "main span"
        ]);

        const classBasedMetadata = getAllItems([
            ".job-details-fit-level-preferences button"
        ]);

        const fallbackMetadata = getAllItems([
            "button[aria-label*='skill' i]",
            "button[aria-label*='experience' i]"
        ]);

        const metadata = uniqueNonEmpty([
            ...(jsonLd?.metadata || []),
            ...classBasedMetadata,
            ...fallbackMetadata
        ]);

        return {
            source: "linkedin",
            extractedAt: new Date().toISOString(),
            url: window.location.href,
            title,
            company,
            location,
            metadata,
            description: jsonLd?.description || getDescription()
        };
    }

    async function extractLinkedInWithRetries() {
        const attempts = 4;
        for (let i = 0; i < attempts; i += 1) {
            const data = extractLinkedInJobDetails();
            if (data.title || data.company || data.description) {
                return data;
            }
            await wait(350);
        }
        return extractLinkedInJobDetails();
    }

    function hasUsefulAtsData(data) {
        if (!data || typeof data !== "object") {
            return false;
        }
        const meaningfulFields = [
            data.company,
            data.role,
            data.location,
            data.description,
            data.requirements,
            data.responsibilities
        ].map((x) => clean(x));

        return meaningfulFields.some(Boolean);
    }

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (!message || message.type !== "EXTRACT_JOB") {
            return;
        }

        (async () => {
            try {
                const currentUrl = window.location.href;
                let data;

                if (currentUrl.includes("linkedin.com/jobs")) {
                    data = await extractLinkedInWithRetries();
                } else if (currentUrl.includes("naukri.com")) {
                    data = extractNaukriJobDetails();
                } else {
                    const atsApi = window.__ATS_EXTRACTORS__;
                    if (atsApi && typeof atsApi.runAtsPipeline === "function") {
                        const atsData = await atsApi.runAtsPipeline();
                        if (hasUsefulAtsData(atsData)) {
                            data = {
                                source: "ats",
                                extractedAt: new Date().toISOString(),
                                url: window.location.href,
                                ...atsData
                            };
                        }
                    }

                    if (!data) {
                        sendResponse({
                            ok: false,
                            error: "Cant extract from this site for now."
                        });
                        return;
                    }
                }

                sendResponse({ ok: true, data });
            } catch (error) {
                sendResponse({
                    ok: false,
                    error: error instanceof Error ? error.message : "Unknown extraction error"
                });
            }
        })();

        return true;
    });
})();
