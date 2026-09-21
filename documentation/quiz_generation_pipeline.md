# Quiz Generation Pipeline — Models, Views, Agentic Design, Celery Tasks

## Celery Tasks Flow

### `generate_quiz_task`

1. Fetch the Quiz data.
2. Set status to `PROCESSING`.
3. Fetch the file path / AWS endpoint.
4. Extract source text using LlamaParse, or Docling as fallback.
5. Save the source text to the database.
6. Chunk the source text and save the chunks to pgvector.
7. On success, call `_run_quiz_generation`; on failure, update the
   status to reflect the failure.

### `_run_quiz_generation()`

1. Build `QuizDetails` from the info passed in from
   `generate_quiz_task`.
2. Initialize the agent state and config, with `thread_id` set to the
   attempt ID (`attempt_id = f"{quiz.pk}-{int(time.time())}"`).
3. Invoke the graph and save the result as the final state.
4. Handle exceptions — a timeout or any other exception is treated as
   a crash.
5. Finally, call `_fetch_trace_data` to get the node-wise cost and
   token breakdown.
6. Save the trace data to `QuizTrace`.
7. If crashed, call `_record_crash()`; otherwise, call
   `_finalize_quiz_generation()`.

### `_finalize_quiz_generation()`

1. Save the quiz's state to `QuizAggregateMetrics`.
2. Log to `QuizGenerationLog`.
3. Save the node-wise cost breakdown to `QuizNodeCost`.
4. On approval, take the generated quiz from the agentic pipeline and
   create the corresponding `Question` and `Answer` objects.
5. Update status to `READY`.
6. On error, update status to `FAILED_API_ERROR`.
7. Otherwise, update status based on the node-level checks.

### `_record_crash()`

1. Save the quiz's state to `QuizAggregateMetrics`.
2. Log to `QuizGenerationLog`.
3. Save the node-wise cost breakdown to `QuizNodeCost`.

### `retry_quiz_task()`

1. Fetch the Quiz data and its source text.
2. Set status to `PROCESSING` again, and invoke
   `_run_quiz_generation()`.

### `resume_quiz_task()`

1. Fetch the Quiz data.
2. Fetch the last trace data from `QuizTrace`.
3. If a last trace is available, fetch its attempt ID.
4. Set the config, and get the state snapshot to check for saved
   state.
5. Invoke the graph with the config.
6. Save the trace data.
7. Invoke `_finalize_quiz_generation()`.

### `cleanup_stuck_quizzes()`

Handles unexpected exceptions — for example, the kill process during
development. Finds quizzes stuck in `PROCESSING` status for the last
20 minutes and sets them to `FAILED_API_ERROR`.


### `generate_quiz_from_text_task()`
 
Reuses the quiz generation pipeline to generate a quiz from an already
-summarized digest, rather than a fresh PDF upload. The digest's
summarized content is stored directly as the source text. The first
user to trigger this generates the quiz from the digest; later users
take the already-generated quiz directly — since the quiz generation
pipeline requires a user to create a quiz, this "first user creates,
rest reuse" pattern lets everyone else skip regenerating it themselves.
 
Note: unlike `generate_quiz_task`, this does **not** chunk the source
text into `SourceChunk` rows — chunking currently only happens for the
PDF-upload path. Digest-generated content is not part of any user's
RAG/retrieval pool for Topics to Preview.
