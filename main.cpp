#define STB_IMAGE_IMPLEMENTATION
#include"stb_image.h"
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include"stb_image_write.h"
#include <iostream>
#include <string>
#include<filesystem>
#include<set>
#include<algorithm>
#include<thread>
#include<mutex>
#include<chrono>
#include<vector>
#include<atomic>


std::mutex mtx;
namespace fs = std::filesystem;


void process(const std::vector<fs::path> files, const std::string& output_dir, std::atomic<int>& count_of_success, std::atomic<int>& count_of_failed){

    for (const auto& file_path : files) {
       
        int width, height, channels;
        unsigned char* img = stbi_load(file_path.string().c_str(), &width, &height, &channels, 0);
        
        if (!img) {
            ++count_of_failed;
            continue;
        }
        
      
        int total_pixels = width * height * channels;
        for (int i = 0; i < total_pixels; i++) {
            img[i] = 255 - img[i];
        }
        std::string filename = file_path.stem().string();
        std::string output_path = output_dir + "/inverted_" + filename + ".png";

        std::unique_lock<std::mutex> lock(mtx);

        std::cout << "Proccessed: " << output_path << std::endl;

        lock.unlock();
        if (!stbi_write_png(output_path.c_str(), width, height, channels, img, width * channels)) {
            ++count_of_failed;
        } else {
            ++count_of_success;
        }
        
        stbi_image_free(img);
    }
}

int main(int argc, char** argv) {

    std::string input_dir;
    std::string output_dir;
    int count_threads;
    if(argc < 3) {
        std::cerr << "Usage: <input_dir> <output_dir>\n" ;
        return 1;
    }
    
    if (argc >= 3) {
        input_dir = argv[1];
        output_dir = argv[2];
        
    }
    
    if (!fs::exists(input_dir)) {
        std::cerr << "Error: Directory '" << input_dir << "' doesn't exist!\n";
        return 1;
    }
    if(!fs::exists(output_dir)) {
        fs::create_directory(output_dir);
    }
    int variant;
    std::cout << "Choose the mode of executing:\n1. One thread\n2. Two threads\n3. A half of threads\n4. All threads\n";
    std::cin >> variant;

    switch (variant)
    {
    case 1:
        count_threads = 1;
        break;
    case 2:
        count_threads = 2;
        break;
    case 3:
        count_threads = std::thread::hardware_concurrency() / 2;
        break;
    case 4:
        count_threads = std::thread::hardware_concurrency();
        break;

    default:
        std::cerr << "Unknown mode" << std::endl;
        break;
        return 1;
    }
    std::set<std::string> extensions = {".png", ".jpeg", ".jpg"};
    
    std::cout << "Proccessing...\n" ;

    //put all files in one vector
    std::vector<fs::path> image_files;
    auto start = std::chrono::high_resolution_clock::now();
      for (const auto& file : fs::directory_iterator(input_dir)) {
        if (file.is_regular_file()) {
            std::string ext = file.path().extension().string();
            
             //check the correctness of extension
            bool supported = find(extensions.begin(), extensions.end(), ext) != extensions.end();
            if(!supported) continue;

            image_files.push_back(file.path());
        }
    }
    
    std::vector<std::vector<fs::path>> pieces(count_threads);
    
    for (size_t i = 0; i < image_files.size(); i++) {
        pieces[i % count_threads].push_back(image_files[i]);
    }

    std::atomic<int> success_count(0);
    std::atomic<int> fail_count(0);
    std::vector<std::thread> threads;


    for (int i = 0; i <  count_threads; i++) {
        threads.emplace_back(process, pieces[i], output_dir, std::ref(success_count), std::ref(fail_count));
                            
    }
    for(auto& thread : threads){
        thread.join();
    }
    auto end = std::chrono::high_resolution_clock::now();

    std:: cout << "Еime of executing: " << (std::chrono::duration_cast<std::chrono::seconds>(end - start)).count() << " seconds" << std::endl;
    std::cout << "Successed: " << success_count << ", failed: " << fail_count << std::endl;
    

}   
