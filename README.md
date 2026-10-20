## OS-Challenge Milestone Submission

This is our submission of the os-challenge project, for the milestone.

We've been working extra hard on it and hope that it is satisfiable. 
While we are already very far along with the project, we still have many ideas on how to improve this and expect to turn in an even faster version with better management of priorities on the final deadline.

## Small Report Preview

This section is meant to serve as a small preview of our report which is still in progress. It is still missing the latest change which has not been formally formatted and is not yet ready to put in the report, however it contains many of our design considerations and results of analysis.
To not dump the entire report in this README, a few of our conclusions based on experiments has been pasted below.

> Note that this is just a way to show our early findings, leading to insight about choices in coding, and does not have to be read.

### Empirical Analysis of Request Distribution Conclusion
The results in this section prove that the bell-shaped distribution hypothesis from Section 1.1.1 is incorrect for the final configuration. This rules out precomputed "hot-zone" caching. Because randomized start values are scattered searches across the entire value space, the "hot-zones" only exist at the relative offset, not the absolute number the hash depends on. On the other hand, caching existing answers was found to be highly effective, cutting overall search work by roughly $20%$ at very minimal cost. Based on these findings, a concurrent hash table keyed by the 32-byte request hash will be implemented. Before running a search, the system will check the cache and immediately store any new answers it finds. High-priority requests are also given priority during both cache lookups and searches, which will help improve the overall priority-weighed score.

### Viability of Shared Search-Space for Batching Conclusion
With the `run-client-final.sh` configuration, two requests with genuinely different answers will essentially never share any part of their search space. Figure 3 and 4's flat "interval overlap" were already suggestive of this, and this section confirms it. Because a batch containing more than one distinct request almost never has a legitimate reason to exist, the proposed batch-selection idea (the combination search, the S(B)|P(B) trade-off, and alpha-beta pruning over the resulting tree) unfortunately has nothing to operate on, and therefore will not be implemented.


### Shared Pool of Work (Single Worker per Request) Conclusion
Under the final workload, the server reaches the highest performance with a small worker pool, reaching its smallest latency at 2 workers. The first transition from one to two workers provides the biggest speed-up by overlapping search execution with request handling, beyond this point, the low concurrency of the workload leaves additional cores idling and introduces thread overhead. For this reason, the worker count should remain low for this configuration rather than scaling to the 16 available cores.

However, this optimum depends heavily on how fast requests come in. If the workload had shorter gaps between requests or sudden traffic spikes, more workers would stay busy, which would shift the ideal worker count higher.

Additionally, these tests only check for assigning one full request per worker. Another strategy is splitting a single request across multiple workers to see if that better utilizes all 16 available CPUs, an approach explored in a subsequent section.
