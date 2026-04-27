## Steps Followed for Urgent Appeal Use Case

### Step 1: Create the urgency and appeal keyword list

Create a complete list of urgency and appeal-related keywords.

Start with the keywords provided by the business team. After that, expand the keyword list using an LLM to cover different forms and variations of the same keyword.

For example, if the business keyword is "urgent", include related forms such as:

urgent, urgently, urgency, expedite, expedited, immediate, priority, time-sensitive

Similarly, for appeal-related scenarios, include words such as:

appeal, appealed, appealing, reconsideration, dispute, grievance

This helps cover different ways in which urgency or appeal intent may appear in the medical chart.

---

### Step 2: Identify pages where the keywords are present

Once the keyword list is ready, scan the chart pages and identify which pages contain those urgency or appeal-related keywords.

Use keyword search techniques such as Regex and RapidFuzz.

Regex can be used for exact keyword matching.

RapidFuzz can be used for fuzzy matching where the keyword may appear in a slightly different form or with minor spelling variations.

For example, if a chart has 100 pages and only 20 pages contain urgency or appeal-related keywords, then only those 20 pages are selected for the next step.

This avoids sending the entire chart to the LLM and helps reduce cost and processing time.

---

### Step 3: Create ground truth for keyword presence

Create the first level of ground truth to confirm whether the keyword is actually present on the selected pages.

This ground truth is only focused on keyword presence, not the actual urgency or appeal intent.

For example:

If the keyword search logic identifies 20 pages out of 100 pages, validate whether those 20 pages really contain the expected keywords.

An advanced reasoning model such as O3 can be used to validate whether the keyword is actually present on each page.

After that, compare the Regex/RapidFuzz output with the ground truth to measure the accuracy of keyword-based page extraction.

---

### Step 4: Measure keyword extraction performance at chart level

Once keyword matching accuracy is available, measure how much time the keyword extraction logic takes at the full chart level.

Run the keyword extraction logic on a larger dataset, such as 200 charts or 1000 XMLs.

Capture the total time taken to process each chart and calculate timing metrics such as:

25th percentile  
50th percentile  
75th percentile  
90th percentile  
99th percentile  

This helps understand the normal, average, and worst-case processing time.

For example:

50th percentile shows the typical processing time.

99th percentile shows the slowest processing cases.

---

### Step 5: Create ground truth for actual urgency or appeal intent

After confirming keyword presence, create a second level of ground truth to check whether the keyword actually represents urgency or appeal intent.

This is important because keyword presence alone does not always mean the page is truly urgent or appeal-related.

For example:

A page may contain the word "appeal", but it may be used in a general context and may not indicate an actual appeal request.

Out of 20 pages where keywords are present, only 5 or 6 pages may truly represent urgency or appeal intent.

Use an advanced reasoning model such as O3 to review the page context and decide whether the page truly indicates urgency or appeal.

---

### Step 6: Pass selected pages to the LLM for intent validation

Once the keyword-matched pages are identified, pass those pages to the LLM to validate the actual intent.

The LLM should review the page content and determine whether the page truly indicates urgency or appeal.

The output should clearly identify whether the page supports an urgency flag, an appeal flag, or no flag.

For example:

If the page clearly says the patient request needs immediate action, then the page can be marked as urgency-related.

If the page clearly mentions an appeal request, then the page can be marked as appeal-related.

If the keyword is present but the context does not support urgency or appeal, then no flag should be marked.

---

### Step 7: Compare individual page processing and batch processing

Test two different LLM processing approaches.

The first approach is individual page processing, where one page is passed to the LLM at a time.

The second approach is batch processing, where multiple pages are passed together in one LLM call.

For example:

10 pages per batch  
20 pages per batch  

Individual page processing may provide better control, but it can take more time because it requires more LLM calls.

Batch processing can reduce the number of LLM calls and improve processing time, but accuracy needs to be validated carefully.

---

### Step 8: Identify the optimum batch size

Compare different batch sizes against the ground truth.

The goal is to find the best batch size where accuracy remains strong and processing time improves.

For example:

If 10 pages per batch gives almost the same accuracy as individual page processing but takes less time, then 10 pages per batch can be considered a better option.

If 20 pages per batch is faster but accuracy drops, then it may not be the right choice.

This step helps find the best balance between accuracy and performance.

---

### Step 9: Measure end-to-end chart-level accuracy

After selecting the best processing approach, test the complete pipeline at the chart level.

This means checking whether the final urgency or appeal flag is correct for the entire chart, not just for individual pages.

For example:

If a chart has 100 pages and only 2 pages truly indicate urgency, the final output should correctly mark the chart as urgency-related.

Run this validation on a larger dataset, such as 200 charts or 1000 XMLs, and compare the final pipeline output with chart-level ground truth.

---

### Step 10: Measure end-to-end chart-level processing time

Finally, measure how much time the complete urgent appeal pipeline takes for each chart.

This should include the full process:

keyword search  
page extraction  
LLM intent validation  
final urgency or appeal flag generation  

Calculate timing metrics such as:

25th percentile  
50th percentile  
75th percentile  
90th percentile  
99th percentile  

This helps understand how the complete pipeline performs in real-world scenarios.

---

## Simple Business Summary

The overall approach is to first identify pages that may contain urgency or appeal-related information using keyword matching.

Then, only those selected pages are passed to the LLM to confirm whether the keyword actually represents urgency or appeal intent.

This approach helps avoid sending the full chart to the LLM, which improves speed and reduces cost.

The solution is then validated in two ways:

1. Whether the keyword search logic correctly finds the right pages.
2. Whether the LLM correctly identifies true urgency or appeal intent from those pages.

Finally, both accuracy and processing time are measured at page level and chart level to select the best production-ready approach.