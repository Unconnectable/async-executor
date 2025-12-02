```rust
// src/lib.rs

pub struct Executor <'a> {
    pub(crate) state : AtomicPtr<State>,
    _marker : PhantomData<std::cell::UnsafeCell<&'a ()>>
}

unsafe impl Send for Executor<'_> { }

unsafe impl Sync for Executor<'_> { }

impl UnwindSafe for Executor<'_> { }

impl RefUnwindSafe for Executor<'_> { }

impl fmt::Debug for Executor<'_> {
    fn fmt (&self, f: &mut fmt::Formatter<'_>) -> fmt::Result;
}

impl <'a> Executor<'a> {
    pub const fn new () -> Executor<'a>;
    pub fn is_empty (&self) -> bool;
    pub fn spawn <T: Send + 'a> (&self, future: impl Future<Output = T> + Send + 'a) -> Task<T>;
    pub fn spawn_many <T: Send + 'a, F: Future<Output = T> + Send + 'a> ( &self, futures: impl IntoIterator<Item = F>, handles: &mut impl Extend<Task<F::Output>>, );
    unsafe fn spawn_inner <T: 'a> ( state: Pin<&'a State>, future: impl Future<Output = T> + 'a, active: &mut Slab<Waker>, ) -> Task<T>;
    pub fn try_tick (&self) -> bool;
    pub async fn tick (&self);
    pub async fn run <T> (&self, future: impl Future<Output = T>) -> T;
    fn schedule (state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a;
    fn state (&self) -> Pin<&'a State>;
}

impl Drop for Executor<'_> {
    fn drop (&mut self);
}

impl <'a> Default for Executor<'a> {
    fn default () -> Executor<'a>;
}

pub struct LocalExecutor <'a> {
    inner : Executor<'a>,
    _marker : PhantomData<Rc<()>>
}

impl UnwindSafe for LocalExecutor<'_> { }

impl RefUnwindSafe for LocalExecutor<'_> { }

impl fmt::Debug for LocalExecutor<'_> {
    fn fmt (&self, f: &mut fmt::Formatter<'_>) -> fmt::Result;
}

impl <'a> LocalExecutor<'a> {
    pub const fn new () -> LocalExecutor<'a>;
    pub fn is_empty (&self) -> bool;
    pub fn spawn <T: 'a> (&self, future: impl Future<Output = T> + 'a) -> Task<T>;
    pub fn spawn_many <T: 'a, F: Future<Output = T> + 'a> ( &self, futures: impl IntoIterator<Item = F>, handles: &mut impl Extend<Task<F::Output>>, );
    pub fn try_tick (&self) -> bool;
    pub async fn tick (&self);
    pub async fn run <T> (&self, future: impl Future<Output = T>) -> T;
    fn inner (&self) -> &Executor<'a>;
}

impl <'a> Default for LocalExecutor<'a> {
    fn default () -> LocalExecutor<'a>;
}

struct State {
    queue : ConcurrentQueue<Runnable>,
    local_queues : RwLock<Vec<Arc<ConcurrentQueue<Runnable>>>>,
    notified : AtomicBool,
    sleepers : Mutex<Sleepers>,
    active : Mutex<Slab<Waker>>
}

impl State {
    const fn new () -> State;
    fn pin (&self) -> Pin<&Self>;
    fn active (self: Pin<&Self>) -> MutexGuard<'_, Slab<Waker>>;
    fn notify (&self);
    pub(crate) fn try_tick (&self) -> bool;
    pub(crate) async fn tick (&self);
    pub async fn run <T> (&self, future: impl Future<Output = T>) -> T;
}

struct Sleepers {
    count : usize,
    wakers : Vec<(usize, Waker)>,
    free_ids : Vec<usize>
}

impl Sleepers {
    fn insert (&mut self, waker: &Waker) -> usize;
    fn update (&mut self, id: usize, waker: &Waker) -> bool;
    fn remove (&mut self, id: usize) -> bool;
    fn is_notified (&self) -> bool;
    fn notify (&mut self) -> Option<Waker>;
}

struct Ticker <'a> {
    state : &'a State,
    sleeping : usize
}

impl Ticker<'_> {
    fn new (state: &State) -> Ticker<'_>;
    fn sleep (&mut self, waker: &Waker) -> bool;
    fn wake (&mut self);
    async fn runnable (&mut self) -> Runnable;
    async fn runnable_with (&mut self, mut search: impl FnMut() -> Option<Runnable>) -> Runnable;
}

impl Drop for Ticker<'_> {
    fn drop (&mut self);
}

struct Runner <'a> {
    state : &'a State,
    ticker : Ticker<'a>,
    local : Arc<ConcurrentQueue<Runnable>>,
    ticks : usize
}

impl Runner<'_> {
    fn new (state: &State) -> Runner<'_>;
    async fn runnable (&mut self, rng: &mut fastrand::Rng) -> Runnable;
}

impl Drop for Runner<'_> {
    fn drop (&mut self);
}

struct CallOnDrop <F: FnMut()>(F);

impl <F: FnMut()> Drop for CallOnDrop<F> {
    fn drop (&mut self);
}

impl <Fut, Cleanup: FnMut()> AsyncCallOnDrop<Fut, Cleanup> {
    fn new (future: Fut, cleanup: Cleanup) -> Self;
}

impl <Fut: Future, Cleanup: FnMut()> Future for AsyncCallOnDrop<Fut, Cleanup> {
    type Output = Fut::Output ;
    fn poll (self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
}
```
