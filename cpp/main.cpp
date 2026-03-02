#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"
#include <iostream>
#include <string>
#include <filesystem>
#include <set>
#include <algorithm>
#include <thread>
#include <mutex>
#include <chrono>
#include <vector>
#include <atomic>
#include<future>
#include<queue>
#include<condition_variable>
#include<shared_mutex>
#include<functional>

std::mutex result_mtx;
std::shared_mutex log_mtx;
namespace fs = std::filesystem;


bool is_digit(char* cstr){

    std::string str(cstr);
    return !str.empty() && std::all_of(str.begin(), str.end(), ::isdigit);
}
template<typename T>
class BlockingQueue {
    std::queue<T> queue_;
    std::mutex mtx;
    std::condition_variable cv;
    std::atomic<bool> is_finished = false;

public:
    void push(const T& item){
        std::unique_lock<std::mutex> lock(mtx);
        queue_.push(item);
        lock.unlock();
        cv.notify_one();
    }
    bool pop(T& item){
        std::unique_lock<std::mutex> lock(mtx);
        cv.wait(lock, [this]
                { return !queue_.empty() || is_finished; });

        if(queue_.empty() && is_finished){
            return false;
        }

        item = queue_.front();
        queue_.pop();
        lock.unlock();
        return true;
    }

    void set_finished() {
        is_finished = true;
        cv.notify_all();
    }

    bool is_empty(){
        std::unique_lock<std::mutex> lock(mtx);
        return queue_.empty();
    }
};

struct ImageTask {
    fs::path input_path;
    std::string output_path;
};

struct ImageResult {
    std::string input_file;
    std::string output_file;
    bool success;
};

void producer(BlockingQueue<ImageTask>& task_queue,
             const std::vector<fs::path>& image_files,
             const std::string& output_dir,
             std::atomic<bool>& complete){
    
    for(const auto& file : image_files){

        std::string filename = file.stem().string();
        std::string output_path = output_dir + "/inverted_" + filename + file.extension().string();

        ImageTask task{file, output_path};

        task_queue.push(task);
        std::unique_lock<std::shared_mutex> lock(log_mtx);
        std::cout << "Producer: Added task for " << file.filename() << std::endl;
    }

    complete.store(true);
    task_queue.set_finished();

              
    {
        std::unique_lock<std::shared_mutex> lock(log_mtx);
        std::cout << "Producer: All tasks added. Total: " << image_files.size() << std::endl;
    }
}

void consumer(BlockingQueue<ImageTask>& task_queue, std::vector<ImageResult>& results, std::atomic<int>& processed_count, int consumer_id ){

    ImageTask task;

    while(task_queue.pop(task)){

        std::unique_lock<std::shared_mutex> lock(log_mtx);
        std::cout << "Consumer " << consumer_id << ": Processing " 
                     << task.input_path.filename() << std::endl;
        lock.unlock();
        
        int width, height, channels;
        unsigned char *img = stbi_load(task.input_path.string().c_str(), &width, &height, &channels, 0);

        ImageResult result;
        result.input_file = task.input_path.string();
        result.output_file = task.output_path;

        if(!img){
            result.success = false;

            lock.lock();
            std::cout << "Consumer " << consumer_id << ": Failed to load "
                      << task.input_path.filename() << std::endl;
            lock.unlock();
        }else{
            int total_pixeles = height * width * channels;
            for (int i = 0; i < total_pixeles; ++i){
                img[i] = 255 - img[i];
            }

            if(!stbi_write_png(task.output_path.c_str(), width, height, channels, img, width * channels)) {
                result.success = false;

            }else{
                result.success = true;

                lock.lock();
                std::cout << "Consumer " << consumer_id << ": Completed "
                          << task.input_path.filename() << std::endl;
            }
        }

        stbi_image_free(img);

        std::unique_lock<std::mutex> lock1(result_mtx);
        results.push_back(result);
        lock1.unlock();
        processed_count++;
    }
    std::unique_lock<std::shared_mutex> lock(log_mtx);
    std::cout << "Consumer " << consumer_id << ": finished work" << std::endl;
}

int main(int argc, char** argv){
    int num_consumers = 4;

    if(argc > 1) {
        num_consumers = std::atoi(argv[1]);
    }

    std::string input_dir = "./dataset";
    std::string output_dir = "./results/images";
    
    if(!fs::exists(input_dir)){
        std::cerr << "Directory " << input_dir << " does not exist!!!\n";
        return -1;
    }

    if(!fs::exists(output_dir)){
        fs::create_directories(output_dir);
    }

    std::set<std::string> extensions = {".png", ".jpeg", ".jpg", ".bmp", ".tiff"};
    std::vector<fs::path> image_files;

    for(const auto& file : fs::directory_iterator(input_dir)){
        if(file.is_regular_file()){
            std::string ext = file.path().extension().string();
            std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

            if(extensions.find(ext) != extensions.end()){
                image_files.push_back(file.path());
            }
        }
    }
    if(image_files.empty()){
        std::cerr << "No image files in directory" << std::endl;
    }

    std::cout << "Found " << image_files.size() << " images to process" << std::endl;
    std::cout << "Using " << num_consumers << " consumer threads" << std::endl;

    BlockingQueue<ImageTask> task_queue;
    std::vector<ImageResult> results;

    std::atomic<int> processed_count(0);
    std::atomic<bool> production_complete(false);

    auto start_time = std::chrono::high_resolution_clock::now();
    
    std::thread producer_thread(producer, std::ref(task_queue), 
                                std::ref(image_files), 
                                std::ref(output_dir),
                                std::ref(production_complete));
    
  
    std::vector<std::thread> consumer_threads;
    for (int i = 0; i < num_consumers; i++){
        consumer_threads.emplace_back(consumer, std::ref(task_queue),
                                      std::ref(results), 
                                      std::ref(processed_count), i);
    }
    

    producer_thread.join();
    
    for (auto& thread : consumer_threads) {
        thread.join();
    }
   
    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::seconds>
                   (end_time - start_time);
    int success_count = 0;
    int fail_count = 0;
    
    for (const auto& result : results){
        if(result.success) {
            success_count++;
        }else{
            fail_count++;
            std::cout << "Failed: " << result.input_file 
                     << std::endl;
        }
    }
    
    std::cout << "\n=== Processing Complete ===" << std::endl;
    std::cout << "Total images: " << image_files.size() << std::endl;
    std::cout << "Successfully processed: " << success_count << std::endl;
    std::cout << "Failed: " << fail_count << std::endl;
    std::cout << "Processing time: " << duration.count() << " stconds" << std::endl;
    
    return 0;
}