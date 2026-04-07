#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cmath>
#include <string>
#include <vector>
#include <tuple>
#include <stdexcept>
#include <algorithm>
#include <sstream>

namespace py = pybind11;

// ======================== Direction ========================
class Direction {
public:
    int dx, dy;

    Direction(int dx = 0, int dy = 0) : dx(dx), dy(dy) {}

    std::string repr() const {
        static const char* names[3][3] = {
            {"south_west", "west", "north_west"},
            {"south", "center", "north"},
            {"south_east", "east", "north_east"}
        };
        return std::string(names[dx + 1][dy + 1]);
    }

    bool equals(const Direction& d) const { return dx == d.dx && dy == d.dy; }
    bool operator==(const Direction& d) const { return equals(d); }

    static Direction center() { return Direction(0, 0); }
    static Direction north() { return Direction(0, 1); }
    static Direction north_east() { return Direction(1, 1); }
    static Direction east() { return Direction(1, 0); }
    static Direction south_east() { return Direction(1, -1); }
    static Direction south() { return Direction(0, -1); }
    static Direction south_west() { return Direction(-1, -1); }
    static Direction west() { return Direction(-1, 0); }
    static Direction north_west() { return Direction(-1, 1); }

    static std::vector<Direction> all_directions() {
        std::vector<Direction> dirs;
        for (int i : {0, -1, 1})
            for (int j : {0, -1, 1})
                dirs.emplace_back(i, j);
        return dirs;
    }

    static std::vector<Direction> cardinal_directions() {
        return {north(), south(), east(), west()};
    }

    int get_dx() const { return dx; }
    int get_dy() const { return dy; }

    Direction opposite() const { return Direction(-dx, -dy); }

    Direction rotate_left() const {
        if (dx == 0 && dy == 0) return center();
        static const Direction ordered[] = {
            east(), north_east(), north(), north_west(),
            west(), south_west(), south(), south_east()
        };
        for (int i = 0; i < 8; i++) {
            if (ordered[i].dx == dx && ordered[i].dy == dy)
                return ordered[(i + 1) % 8];
        }
        return center();
    }

    Direction rotate_right() const {
        if (dx == 0 && dy == 0) return center();
        static const Direction ordered[] = {
            east(), north_east(), north(), north_west(),
            west(), south_west(), south(), south_east()
        };
        for (int i = 0; i < 8; i++) {
            if (ordered[i].dx == dx && ordered[i].dy == dy)
                return ordered[(i + 7) % 8];
        }
        return center();
    }
};

// ======================== MapLocation ========================
class MapLocation {
public:
    int x, y;

    MapLocation(int x = 0, int y = 0) : x(x), y(y) {}

    std::string repr() const {
        std::ostringstream oss;
        oss << "(" << x << ", " << y << ")";
        return oss.str();
    }

    bool equals(const MapLocation& loc) const { return x == loc.x && y == loc.y; }
    bool operator==(const MapLocation& loc) const { return equals(loc); }

    MapLocation add(const Direction& d) const { return MapLocation(x + d.dx, y + d.dy); }

    Direction direction_to(const MapLocation& loc) const {
        int ddx = loc.x - x;
        int ddy = loc.y - y;
        if (ddx > 0) ddx = 1; else if (ddx < 0) ddx = -1;
        if (ddy > 0) ddy = 1; else if (ddy < 0) ddy = -1;
        return Direction(ddx, ddy);
    }

    int distance_to(const MapLocation& loc) const {
        int ddx = loc.x - x;
        int ddy = loc.y - y;
        return ddx * ddx + ddy * ddy;
    }

    bool is_adjacent_to(const MapLocation& loc) const {
        return std::abs(x - loc.x) <= 1 && std::abs(y - loc.y) <= 1;
    }

    MapLocation subtract(const Direction& d) const { return MapLocation(x - d.dx, y - d.dy); }
    MapLocation translate(int ddx, int ddy) const { return MapLocation(x + ddx, y + ddy); }

    std::tuple<int, int> to_tuple() const { return {x, y}; }
};

// ======================== EntityType ========================
class EntityType {
public:
    std::string name;
    double action_cooldown;
    int action_radius;
    double defence_ratio;
    int detection_radius;
    int initial_cooldown;
    int sensor_radius;

    EntityType(const std::string& entity_type) {
        if (entity_type == "destroyer") {
            name = entity_type; action_cooldown = 1.0; action_radius = 9;
            defence_ratio = 1.0; detection_radius = 25; initial_cooldown = 10; sensor_radius = 25;
        } else if (entity_type == "miner") {
            name = entity_type; action_cooldown = 2.0; action_radius = 0;
            defence_ratio = 1.0; detection_radius = 20; initial_cooldown = 0; sensor_radius = 20;
        } else if (entity_type == "scout") {
            name = entity_type; action_cooldown = 1.5; action_radius = 12;
            defence_ratio = 0.7; detection_radius = 40; initial_cooldown = 10; sensor_radius = 30;
        } else if (entity_type == "planet") {
            name = entity_type; action_cooldown = 2.0; action_radius = 2;
            defence_ratio = 1.0; detection_radius = 40; initial_cooldown = 0; sensor_radius = 40;
        } else {
            throw std::runtime_error("无效的种类。");
        }
    }

    std::string repr() const { return name; }
    bool operator==(const EntityType& other) const { return name == other.name; }
    bool eq_str(const std::string& s) const { return name == s; }

    static std::vector<EntityType> all_types() {
        return {EntityType("destroyer"), EntityType("miner"), EntityType("scout"), EntityType("planet")};
    }
};

// ======================== Team ========================
class Team {
public:
    std::string tag;

    Team(const std::string& team) : tag(team) {}

    std::string repr() const { return tag; }
    bool operator==(const Team& other) const { return tag == other.tag; }
    bool eq_str(const std::string& s) const { return tag == s; }
    bool is_player() const { return tag != "Neutral"; }
};

// ======================== EntityInfo ========================
class EntityInfo {
public:
    int energy;
    int defence;
    int init_defence;
    int ID;
    MapLocation location;
    Team team;
    EntityType type;
    int radio;

    EntityInfo(int defence, int rid, int energy, MapLocation location, Team team, EntityType rtype, int radio)
        : energy(energy),
          defence(rtype.name != "planet" ? defence : energy),
          init_defence(defence),
          ID(rid),
          location(location),
          team(team),
          type(rtype),
          radio(radio) {}

    EntityInfo copy() const {
        return EntityInfo(defence, ID, energy, location, team, type, radio);
    }

    py::dict to_dict() const {
        py::dict d;
        d["ID"] = ID;
        d["energy"] = energy;
        d["defence"] = defence;
        d["location"] = location.to_tuple();
        d["team"] = team.tag;
        d["type"] = type.name;
        d["radio"] = radio;
        return d;
    }
};

// ======================== Map ========================
class Map {
public:
    std::vector<std::vector<double>> content;
    int width, height, dx, dy;

    Map(const std::vector<py::dict>& aether_dense, std::tuple<int, int> map_size, int dx = 0, int dy = 0)
        : width(std::get<0>(map_size)), height(std::get<1>(map_size)), dx(dx), dy(dy) {
        content.resize(width);
        for (int i = 0; i < width; i++) {
            content[i].resize(height, 0.0);
        }
        for (auto& block : aether_dense) {
            int bx = block["x"].cast<int>();
            int by = block["y"].cast<int>();
            double aether = block["aether"].cast<double>();
            if (bx >= 0 && bx < width && by >= 0 && by < height)
                content[bx][by] = aether;
        }
    }

    double get_aether(int x, int y) const {
        return content[x - dx][y - dy];
    }

    bool include(int x, int y) const {
        return (dx <= x && x < dx + width) && (dy <= y && y < dy + height);
    }

    py::dict to_dict() const {
        py::dict d;
        // Convert content to Python list of lists
        py::list outer;
        for (auto& row : content) {
            py::list inner;
            for (double v : row)
                inner.append(v);
            outer.append(inner);
        }
        d["content"] = outer;
        d["size"] = py::make_tuple(width, height);
        d["origin"] = py::make_tuple(dx, dy);
        return d;
    }
};

// ======================== Controller ========================
class Controller {
public:
    EntityInfo info_;
    double cooldown_;
    std::vector<EntityInfo> sensed_entities_;
    std::vector<MapLocation> detected_entities_;
    std::vector<Team> teams_info_;
    int charge_point_;
    Map* map_;
    int round_count_;
    py::list overdrive_factor_;
    int entity_count_;

    // action state
    int charged_;
    bool to_create_;
    py::list create_param_;
    bool to_overdrive_;
    int overdrive_range_;
    bool to_analyze_;
    py::object analyze_target_;

    Controller(EntityInfo info, std::vector<EntityInfo> sensed_entities,
               std::vector<MapLocation> detected_entities, std::vector<Team> teams_info,
               int charge_point, Map* gmap, double cooldown, int round_count,
               py::list overdrive_factor, int entity_count)
        : info_(info), cooldown_(cooldown), sensed_entities_(std::move(sensed_entities)),
          detected_entities_(std::move(detected_entities)), teams_info_(std::move(teams_info)),
          charge_point_(charge_point), map_(gmap), round_count_(round_count),
          overdrive_factor_(overdrive_factor), entity_count_(entity_count),
          charged_(0), to_create_(false), to_overdrive_(false),
          overdrive_range_(0), to_analyze_(false), analyze_target_(py::none()) {}

    // Helper: search by location
    py::object search_by_loc(const MapLocation& loc) const {
        for (auto& info : sensed_entities_) {
            if (info.location == loc)
                return py::cast(info);
        }
        return py::none();
    }

    // Helper: search by ID
    py::object search_by_id(int rid) const {
        for (auto& info : sensed_entities_) {
            if (info.ID == rid)
                return py::cast(info);
        }
        return py::none();
    }

    double get_cooldown_val(double base_cooldown) const {
        return base_cooldown / map_->get_aether(info_.location.x, info_.location.y);
    }

    std::vector<Team> get_all_teams() const { return teams_info_; }

    std::vector<Team> get_opponent() const {
        std::vector<Team> result;
        for (auto& t : teams_info_) {
            if (!(t == get_team())) result.push_back(t);
        }
        return result;
    }

    int get_cooldown_turns() const { return (int)cooldown_; }

    double get_overdrive_factor(const Team& team, int round = 0) const {
        if (round < 0) throw std::runtime_error("轮数必须为非负数。");
        double index = 0;
        for (auto item : overdrive_factor_) {
            py::list lst = item.cast<py::list>();
            std::string tag = lst[0].cast<std::string>();
            double energy = lst[1].cast<double>();
            int expire_round = lst[2].cast<int>();
            if (team.tag == tag && expire_round > round_count_ + round)
                index += energy;
        }
        return std::pow(1.001, index);
    }

    int get_defence() const { return info_.defence; }
    int get_id() const { return info_.ID; }
    int get_energy() const { return info_.energy; }
    MapLocation get_location() const { return info_.location; }
    int get_round_num() const { return round_count_; }
    Team get_team() const { return info_.team; }
    EntityType get_type() const { return info_.type; }
    int get_radio() const { return info_.radio; }
    int get_charge_point() const { return charge_point_; }
    int get_entity_count() const { return entity_count_; }

    MapLocation adjacent_location(const Direction& d) const {
        return info_.location.add(d);
    }

    bool is_opponent(const Team& team) const {
        return !(info_.team == team);
    }

    bool is_blocked(const Direction& d) const {
        MapLocation loc = adjacent_location(d);
        for (auto& info : sensed_entities_) {
            if (info.location == loc) return true;
        }
        return false;
    }

    bool is_location_occupied(const MapLocation& loc) const {
        if (info_.location.distance_to(loc) > info_.type.detection_radius)
            throw std::runtime_error("超出探测范围。");
        if (!on_the_map(loc))
            throw std::runtime_error("指定位置不在地图上。");
        for (auto& entity : detected_entities_) {
            if (entity == loc) return true;
        }
        return false;
    }

    bool is_ready() const { return cooldown_ < 1.0; }

    bool on_the_map(const MapLocation& loc) const {
        if (info_.location.distance_to(loc) > info_.type.detection_radius)
            throw std::runtime_error("超出探测范围。");
        return map_->include(loc.x, loc.y);
    }

    bool can_detect_location(const MapLocation& loc) const {
        return info_.location.distance_to(loc) <= info_.type.detection_radius && map_->include(loc.x, loc.y);
    }

    bool can_detect_radius(int radius) const {
        return radius <= info_.type.detection_radius;
    }

    bool can_sense_location(const MapLocation& loc) const {
        if (info_.location.distance_to(loc) <= info_.type.sensor_radius) {
            // Need to check on_the_map without the detection_radius check
            return map_->include(loc.x, loc.y);
        }
        return false;
    }

    bool can_sense_radius(int radius) const {
        return info_.type.sensor_radius >= radius;
    }

    py::object sense_entity_by_id(int rid) const {
        return search_by_id(rid);
    }

    py::object sense_entity_by_loc(const MapLocation& loc) const {
        return search_by_loc(loc);
    }

    std::vector<EntityInfo> sense_nearby_entities(
        py::object center_obj = py::none(), py::object radius_obj = py::none(),
        py::object teams_obj = py::none()) const
    {
        MapLocation center = center_obj.is_none() ? info_.location : center_obj.cast<MapLocation>();
        int radius = radius_obj.is_none() ? info_.type.sensor_radius : radius_obj.cast<int>();

        std::vector<EntityInfo> entities;
        for (auto& entity : sensed_entities_) {
            if (entity.location.distance_to(center) <= radius) {
                if (teams_obj.is_none()) {
                    entities.push_back(entity);
                } else {
                    auto teams = teams_obj.cast<std::vector<Team>>();
                    for (auto& t : teams) {
                        if (entity.team == t) {
                            entities.push_back(entity);
                            break;
                        }
                    }
                }
            }
        }
        return entities;
    }

    std::vector<MapLocation> detect_nearby_entities(int radius) const {
        std::vector<MapLocation> locs;
        for (auto& entity : detected_entities_) {
            if (entity.distance_to(info_.location) <= radius)
                locs.push_back(entity);
        }
        return locs;
    }

    double sense_aether(const MapLocation& loc) const {
        if (loc.distance_to(info_.location) > info_.type.sensor_radius)
            throw std::runtime_error("超出感知范围。");
        if (!map_->include(loc.x, loc.y))
            throw std::runtime_error("目标不在地图上。");
        return map_->get_aether(loc.x, loc.y);
    }

    bool can_charge(int energy) const {
        return info_.type.name == "planet" && info_.energy >= energy && energy >= 0;
    }

    bool can_build(const EntityType& entity_type, const Direction& d, int energy) const {
        energy = (int)energy;
        MapLocation adj = adjacent_location(d);
        bool blocked = false;
        for (auto& info : sensed_entities_) {
            if (info.location == adj) { blocked = true; break; }
        }
        return info_.type.name == "planet" && entity_type.name != "planet" &&
               !blocked && info_.energy >= energy && energy > 0 &&
               is_ready() && map_->include(adj.x, adj.y);
    }

    bool can_overdrive(int radius) const {
        return info_.type.name == "destroyer" && radius <= info_.type.action_radius && is_ready();
    }

    bool can_analyze_by_id(int rid) const {
        if (info_.type.name == "scout" && is_ready()) {
            for (auto& info : sensed_entities_) {
                if (info.ID == rid) {
                    if (info.location.distance_to(info_.location) <= info_.type.action_radius)
                        return true;
                }
            }
        }
        return false;
    }

    bool can_analyze_by_loc(const MapLocation& loc) const {
        if (info_.type.name == "scout" && is_ready()) {
            for (auto& info : sensed_entities_) {
                if (info.location == loc) {
                    if (info.location.distance_to(info_.location) <= info_.type.action_radius)
                        return true;
                }
            }
        }
        return false;
    }

    bool can_move(const Direction& d) const {
        MapLocation adj = adjacent_location(d);
        bool blocked = false;
        for (auto& info : sensed_entities_) {
            if (info.location == adj) { blocked = true; break; }
        }
        return is_ready() && !blocked && map_->include(adj.x, adj.y);
    }

    static bool can_set_radio(int radio) {
        return radio >= 0 && radio <= (1 << 28) - 1;
    }

    void charge(int energy) {
        energy = (int)energy;
        if (info_.type.name != "planet") throw std::runtime_error("只有星球可以充能。");
        if (info_.energy < energy) throw std::runtime_error("能量不足。");
        if (energy < 0) throw std::runtime_error("能量必须为正整数。");
        info_.energy -= energy;
        charged_ = energy;
    }

    void build(const EntityType& entity_type, const Direction& d, int energy) {
        energy = (int)energy;
        if (info_.type.name != "planet") throw std::runtime_error("只有星球可以建造。");
        if (entity_type.name == "planet") throw std::runtime_error("星球无法被建造。");
        MapLocation adj = adjacent_location(d);
        bool blocked = false;
        for (auto& info : sensed_entities_) {
            if (info.location == adj) { blocked = true; break; }
        }
        if (blocked) throw std::runtime_error("目标位置被阻塞。");
        if (!map_->include(adj.x, adj.y)) throw std::runtime_error("目标位置不在地图上。");
        if (info_.energy < energy) throw std::runtime_error("能量不足。");
        if (energy <= 0) throw std::runtime_error("能量必须为正整数。");
        if (!is_ready()) throw std::runtime_error("冷却值必须小于 1。");

        info_.energy -= energy;
        cooldown_ += get_cooldown_val(info_.type.action_cooldown);
        to_create_ = true;
        create_param_ = py::list();
        create_param_.append(py::cast(entity_type));
        create_param_.append(py::cast(d));
        create_param_.append(energy);
    }

    void overdrive(int radius) {
        if (info_.type.name != "destroyer") throw std::runtime_error("只有战列舰可以过载。");
        if (!can_overdrive(radius)) throw std::runtime_error("无法以指定的参数过载。");
        if (!is_ready()) throw std::runtime_error("冷却值必须小于 1。");
        to_overdrive_ = true;
        overdrive_range_ = radius;
        cooldown_ += get_cooldown_val(info_.type.action_cooldown);
    }

    void analyze_by_id(int rid) {
        if (info_.type.name != "scout") throw std::runtime_error("只有侦查舰可以分析。");
        if (!can_analyze_by_id(rid)) throw std::runtime_error("无法以指定的参数分析。");
        if (!is_ready()) throw std::runtime_error("冷却值必须小于 1。");
        for (auto& info : sensed_entities_) {
            if (info.ID == rid) {
                to_analyze_ = true;
                analyze_target_ = py::cast(info);
                info_.defence = std::max(info_.defence - 10, 0);
                cooldown_ += get_cooldown_val(info_.type.action_cooldown);
                return;
            }
        }
    }

    void analyze_by_loc(const MapLocation& loc) {
        if (info_.type.name != "scout") throw std::runtime_error("只有侦查舰可以分析。");
        if (!can_analyze_by_loc(loc)) throw std::runtime_error("无法以指定的参数分析。");
        if (!is_ready()) throw std::runtime_error("冷却值必须小于 1。");
        for (auto& info : sensed_entities_) {
            if (info.location == loc) {
                to_analyze_ = true;
                analyze_target_ = py::cast(info);
                info_.defence = std::max(info_.defence - 10, 0);
                cooldown_ += get_cooldown_val(info_.type.action_cooldown);
                return;
            }
        }
    }

    void move(const Direction& d) {
        if (!is_ready()) throw std::runtime_error("冷却值必须小于 1。");
        MapLocation adj = adjacent_location(d);
        bool blocked = false;
        for (auto& info : sensed_entities_) {
            if (info.location == adj) { blocked = true; break; }
        }
        if (blocked) throw std::runtime_error("目标位置被阻塞。");
        if (info_.type.name == "planet") throw std::runtime_error("星球无法移动。");
        if (!map_->include(adj.x, adj.y)) throw std::runtime_error("目标位置不在地图上。");
        info_.location = adj;
        cooldown_ += get_cooldown_val(info_.type.action_cooldown);
    }

    void set_radio(int radio) {
        if (!can_set_radio(radio)) throw std::runtime_error("广播值超出范围。");
        info_.radio = radio;
    }

    py::tuple get_actions() {
        py::list actions;
        if (info_.type.name == "planet") {
            if (to_create_) {
                py::list action;
                action.append("create");
                action.append(create_param_);
                actions.append(action);
            }
            py::list charge_action;
            charge_action.append("charge");
            charge_action.append(charged_);
            actions.append(charge_action);
            info_.defence = info_.energy;
        } else if (info_.type.name == "destroyer") {
            if (to_overdrive_) {
                py::list action;
                action.append("overdrive");
                action.append(overdrive_range_);
                actions.append(action);
            }
        } else if (info_.type.name == "scout") {
            if (to_analyze_) {
                py::list action;
                action.append("analyze");
                action.append(analyze_target_);
                actions.append(action);
            }
        }
        return py::make_tuple(py::cast(info_), cooldown_, actions);
    }
};

// ======================== Entity ========================
class Entity {
public:
    EntityInfo info;
    double cooldown;
    int created_round;
    int created_planet;

    Entity(const EntityType& rtype, int energy, const MapLocation& location, const Team& team, int cround, py::object cplanet, int rid)
        : info(EntityInfo((int)std::ceil(energy * rtype.defence_ratio), rid, energy, location, team, rtype, 0)),
          cooldown(rtype.initial_cooldown),
          created_round(cround),
          created_planet(cplanet.is_none() ? -1 : cplanet.cast<int>()) {}

    Controller get_controller(const std::vector<EntityInfo>& all_entities,
                              const std::vector<Team>& teams_info,
                              const std::vector<int>& charge_result,
                              Map& gmap, int round_count, py::list overdrive_factor) {
        std::vector<EntityInfo> sensed_entities;
        std::vector<MapLocation> detected_entities;
        int entity_cnt = 0;
        int det_r = info.type.detection_radius;
        int sen_r = info.type.sensor_radius;
        bool is_destroyer_or_miner = (info.type.name == "destroyer" || info.type.name == "miner");

        for (auto& entity : all_entities) {
            if (entity.team == info.team)
                entity_cnt++;
            int d = entity.location.distance_to(info.location);
            if (d <= det_r) {
                detected_entities.push_back(entity.location);
                if (d <= sen_r) {
                    EntityInfo new_entity = entity.copy();
                    if (is_destroyer_or_miner && entity.type.name == "miner" && entity.ID != info.ID) {
                        new_entity.type = EntityType("destroyer");
                    }
                    sensed_entities.push_back(new_entity);
                }
            }
        }

        int team_tag = std::stoi(info.team.tag);
        return Controller(info, std::move(sensed_entities), std::move(detected_entities),
                          teams_info, charge_result[team_tag], &gmap, cooldown, round_count,
                          overdrive_factor, entity_cnt);
    }
};


// ======================== Engine Functions ========================

// Compute overdrive factor from the global list
double engine_get_overdrive_factor(
    const py::list& overdrive_factor, const std::string& team_tag, int current_round)
{
    double index = 0;
    for (auto item : overdrive_factor) {
        py::tuple tup = item.cast<py::tuple>();
        std::string tag = tup[0].cast<std::string>();
        double energy = tup[1].cast<double>();
        int expire_round = tup[2].cast<int>();
        if (tag == team_tag && expire_round > current_round)
            index += energy;
    }
    return std::pow(1.001, std::min(1145.0, index));
}

// Process overdrive effects on all available entities
// entity_ids: list of available entity IDs
// entity_infos: corresponding EntityInfo for each ID (same order)
// attacker: info of the overdrive entity
// radius: overdrive radius
// odfactor: precomputed overdrive factor
// Returns list of tuples: (entity_id, new_energy, new_defence, new_team_tag, should_remove)
py::list engine_process_overdrive(
    const std::vector<int>& entity_ids,
    const std::vector<EntityInfo>& entity_infos,
    const EntityInfo& attacker,
    int radius,
    double odfactor)
{
    py::list results;
    if (attacker.defence <= 10) return results;

    // Find targets in radius
    std::vector<size_t> target_indices;
    for (size_t i = 0; i < entity_ids.size(); i++) {
        if (entity_infos[i].location.distance_to(attacker.location) <= radius)
            target_indices.push_back(i);
    }

    if (target_indices.empty()) return results;

    int amount = (int)((attacker.defence - 10.0) / target_indices.size() * odfactor);

    for (size_t idx : target_indices) {
        int rid = entity_ids[idx];
        const EntityInfo& ei = entity_infos[idx];
        int new_energy = ei.energy;
        int new_defence = ei.defence;
        std::string new_team;  // empty = unchanged
        bool should_remove = false;

        if (ei.team == attacker.team) {
            // Friendly
            if (ei.type.name == "planet") {
                new_energy += amount;
            } else {
                new_defence = std::min(new_defence + amount, ei.init_defence);
            }
        } else {
            // Enemy
            if (ei.type.name == "planet") {
                new_energy -= amount;
                if (new_energy < 0) {
                    new_energy = -new_energy;
                    new_team = attacker.team.tag;
                }
            } else if (ei.type.name == "destroyer") {
                new_defence -= amount;
                if (new_defence < 0) {
                    new_defence = std::min(-new_defence, ei.init_defence);
                    new_team = attacker.team.tag;
                } else if (new_defence == 0) {
                    should_remove = true;
                }
            } else {
                // miner or scout
                new_defence -= amount;
                if (new_defence <= 0) {
                    should_remove = true;
                }
            }
        }
        results.append(py::make_tuple(rid, new_energy, new_defence, new_team, should_remove));
    }
    return results;
}

// Compute miner income for the mother planet
int engine_compute_miner_income(int energy) {
    return (int)std::floor((0.02 + 0.03 * std::exp(-0.001 * energy)) * energy);
}

// Process charge round resolution
// charge_list: list of (entity_id, energy) pairs
// Returns (winner_team_idx_or_neg1, list of (entity_id, energy_return))
py::tuple engine_process_charge(
    const std::vector<std::pair<int, int>>& charge_list,
    const std::vector<std::string>& charge_team_tags)
{
    py::list returns;
    if (charge_list.empty())
        return py::make_tuple(-1, returns);

    int max_energy = -1;
    for (auto& [id, e] : charge_list)
        max_energy = std::max(max_energy, e);

    std::vector<int> max_planets;
    for (size_t i = 0; i < charge_list.size(); i++) {
        if (charge_list[i].second == max_energy)
            max_planets.push_back((int)i);
    }

    if (max_planets.size() == 1) {
        int winner_idx = max_planets[0];
        int winner_team = std::stoi(charge_team_tags[winner_idx]);
        for (size_t i = 0; i < charge_list.size(); i++) {
            if ((int)i != winner_idx)
                returns.append(py::make_tuple(charge_list[i].first, (int)std::floor(charge_list[i].second / 2.0)));
        }
        return py::make_tuple(winner_team, returns);
    } else {
        for (size_t i = 0; i < charge_list.size(); i++)
            returns.append(py::make_tuple(charge_list[i].first, (int)std::floor(charge_list[i].second / 2.0)));
        return py::make_tuple(-1, returns);
    }
}

// Check round end conditions
// Returns (alive_team_tags, miner_evolution_ids)
py::tuple engine_check_round_end(
    const std::vector<int>& entity_ids,
    const std::vector<std::string>& team_tags,
    const std::vector<std::string>& type_names,
    const std::vector<int>& created_rounds,
    int current_round)
{
    py::list alive_teams;
    py::list evolutions;
    std::vector<std::string> seen_teams;

    for (size_t i = 0; i < entity_ids.size(); i++) {
        // Alive teams
        bool found = false;
        for (auto& t : seen_teams) {
            if (t == team_tags[i]) { found = true; break; }
        }
        if (!found) {
            seen_teams.push_back(team_tags[i]);
            alive_teams.append(py::str(team_tags[i]));
        }
        // Miner evolution
        if (type_names[i] == "miner" && current_round >= created_rounds[i] + 300) {
            evolutions.append(entity_ids[i]);
        }
    }
    return py::make_tuple(alive_teams, evolutions);
}


// ======================== PYBIND11 MODULE ========================
PYBIND11_MODULE(cosmos_core, m) {
    m.doc() = "Cosmos game core C++ acceleration module";

    py::class_<Direction>(m, "Direction")
        .def(py::init<int, int>(), py::arg("dx") = 0, py::arg("dy") = 0)
        .def_readwrite("dx", &Direction::dx)
        .def_readwrite("dy", &Direction::dy)
        .def("__repr__", &Direction::repr)
        .def("__str__", &Direction::repr)
        .def("__eq__", [](const Direction& self, const py::object& other) {
            if (py::isinstance<Direction>(other))
                return self == other.cast<Direction>();
            return false;
        })
        .def_static("center", &Direction::center)
        .def_static("north", &Direction::north)
        .def_static("north_east", &Direction::north_east)
        .def_static("east", &Direction::east)
        .def_static("south_east", &Direction::south_east)
        .def_static("south", &Direction::south)
        .def_static("south_west", &Direction::south_west)
        .def_static("west", &Direction::west)
        .def_static("north_west", &Direction::north_west)
        .def_static("all_directions", &Direction::all_directions)
        .def_static("cardinal_directions", &Direction::cardinal_directions)
        .def("get_dx", &Direction::get_dx)
        .def("get_dy", &Direction::get_dy)
        .def("opposite", &Direction::opposite)
        .def("rotate_left", &Direction::rotate_left)
        .def("rotate_right", &Direction::rotate_right)
        .def("equals", &Direction::equals);

    py::class_<MapLocation>(m, "MapLocation")
        .def(py::init<int, int>(), py::arg("x") = 0, py::arg("y") = 0)
        .def_readwrite("x", &MapLocation::x)
        .def_readwrite("y", &MapLocation::y)
        .def("__repr__", &MapLocation::repr)
        .def("__str__", &MapLocation::repr)
        .def("__eq__", [](const MapLocation& self, const py::object& other) {
            if (py::isinstance<MapLocation>(other))
                return self == other.cast<MapLocation>();
            return false;
        })
        .def("add", &MapLocation::add)
        .def("direction_to", &MapLocation::direction_to)
        .def("distance_to", &MapLocation::distance_to)
        .def("is_adjacent_to", &MapLocation::is_adjacent_to)
        .def("subtract", &MapLocation::subtract)
        .def("translate", &MapLocation::translate)
        .def("equals", &MapLocation::equals)
        .def("to_tuple", &MapLocation::to_tuple);

    py::class_<EntityType>(m, "EntityType")
        .def(py::init<const std::string&>())
        .def_readwrite("name", &EntityType::name)
        .def_readwrite("action_cooldown", &EntityType::action_cooldown)
        .def_readwrite("action_radius", &EntityType::action_radius)
        .def_readwrite("defence_ratio", &EntityType::defence_ratio)
        .def_readwrite("detection_radius", &EntityType::detection_radius)
        .def_readwrite("initial_cooldown", &EntityType::initial_cooldown)
        .def_readwrite("sensor_radius", &EntityType::sensor_radius)
        .def("__repr__", &EntityType::repr)
        .def("__str__", &EntityType::repr)
        .def("__eq__", [](const EntityType& self, const py::object& other) {
            if (py::isinstance<EntityType>(other))
                return self == other.cast<EntityType>();
            if (py::isinstance<py::str>(other))
                return self.eq_str(other.cast<std::string>());
            return false;
        })
        .def_static("all_types", &EntityType::all_types);

    py::class_<Team>(m, "Team")
        .def(py::init<const std::string&>())
        .def_readwrite("tag", &Team::tag)
        .def("__repr__", &Team::repr)
        .def("__str__", &Team::repr)
        .def("__eq__", [](const Team& self, const py::object& other) {
            if (py::isinstance<Team>(other))
                return self == other.cast<Team>();
            if (py::isinstance<py::str>(other))
                return self.eq_str(other.cast<std::string>());
            return false;
        })
        .def("is_player", &Team::is_player);

    py::class_<EntityInfo>(m, "EntityInfo")
        .def(py::init<int, int, int, MapLocation, Team, EntityType, int>())
        .def_readwrite("energy", &EntityInfo::energy)
        .def_readwrite("defence", &EntityInfo::defence)
        .def_readwrite("init_defence", &EntityInfo::init_defence)
        .def_readwrite("ID", &EntityInfo::ID)
        .def_readwrite("location", &EntityInfo::location)
        .def_readwrite("team", &EntityInfo::team)
        .def_readwrite("type", &EntityInfo::type)
        .def_readwrite("radio", &EntityInfo::radio)
        .def("copy", &EntityInfo::copy)
        .def("to_dict", &EntityInfo::to_dict);

    py::class_<Map>(m, "Map")
        .def(py::init<const std::vector<py::dict>&, std::tuple<int, int>, int, int>(),
             py::arg("aether_dense"), py::arg("map_size"), py::arg("dx") = 0, py::arg("dy") = 0)
        .def_readwrite("content", &Map::content)
        .def_readwrite("width", &Map::width)
        .def_readwrite("height", &Map::height)
        .def_readwrite("dx", &Map::dx)
        .def_readwrite("dy", &Map::dy)
        .def("get_aether", &Map::get_aether)
        .def("include", &Map::include)
        .def("to_dict", &Map::to_dict);

    py::class_<Controller>(m, "Controller")
        .def(py::init<EntityInfo, std::vector<EntityInfo>, std::vector<MapLocation>,
                       std::vector<Team>, int, Map*, double, int, py::list, int>())
        .def("get_all_teams", &Controller::get_all_teams)
        .def("get_opponent", &Controller::get_opponent)
        .def("get_cooldown_turns", &Controller::get_cooldown_turns)
        .def("get_overdrive_factor", &Controller::get_overdrive_factor, py::arg("team"), py::arg("round") = 0)
        .def("get_defence", &Controller::get_defence)
        .def("get_id", &Controller::get_id)
        .def("get_energy", &Controller::get_energy)
        .def("get_location", &Controller::get_location)
        .def("get_round_num", &Controller::get_round_num)
        .def("get_team", &Controller::get_team)
        .def("get_type", &Controller::get_type)
        .def("get_radio", &Controller::get_radio)
        .def("get_charge_point", &Controller::get_charge_point)
        .def("get_entity_count", &Controller::get_entity_count)
        .def("adjacent_location", &Controller::adjacent_location)
        .def("is_opponent", &Controller::is_opponent)
        .def("is_blocked", &Controller::is_blocked)
        .def("is_location_occupied", &Controller::is_location_occupied)
        .def("is_ready", &Controller::is_ready)
        .def("on_the_map", &Controller::on_the_map)
        .def("can_detect_location", &Controller::can_detect_location)
        .def("can_detect_radius", &Controller::can_detect_radius)
        .def("can_sense_location", &Controller::can_sense_location)
        .def("can_sense_radius", &Controller::can_sense_radius)
        .def("sense_entity", [](const Controller& self, py::object arg) -> py::object {
            if (py::isinstance<py::int_>(arg))
                return self.sense_entity_by_id(arg.cast<int>());
            if (py::isinstance<MapLocation>(arg))
                return self.sense_entity_by_loc(arg.cast<MapLocation>());
            return py::none();
        })
        .def("sense_nearby_entities", &Controller::sense_nearby_entities,
             py::arg("center") = py::none(), py::arg("radius") = py::none(), py::arg("teams") = py::none())
        .def("detect_nearby_entities", &Controller::detect_nearby_entities)
        .def("sense_aether", &Controller::sense_aether)
        .def("can_charge", &Controller::can_charge)
        .def("can_build", &Controller::can_build)
        .def("can_overdrive", &Controller::can_overdrive)
        .def("can_analyze", [](const Controller& self, py::object arg) -> bool {
            if (py::isinstance<py::int_>(arg))
                return self.can_analyze_by_id(arg.cast<int>());
            if (py::isinstance<MapLocation>(arg))
                return self.can_analyze_by_loc(arg.cast<MapLocation>());
            return false;
        })
        .def("can_move", &Controller::can_move)
        .def_static("can_set_radio", &Controller::can_set_radio)
        .def("charge", &Controller::charge)
        .def("build", &Controller::build)
        .def("overdrive", &Controller::overdrive)
        .def("analyze", [](Controller& self, py::object arg) {
            if (py::isinstance<py::int_>(arg))
                self.analyze_by_id(arg.cast<int>());
            else if (py::isinstance<MapLocation>(arg))
                self.analyze_by_loc(arg.cast<MapLocation>());
            else
                throw std::runtime_error("无法以指定的参数分析。");
        })
        .def("move", &Controller::move)
        .def("set_radio", &Controller::set_radio)
        .def("get_actions", &Controller::get_actions);

    py::class_<Entity>(m, "Entity")
        .def(py::init<const EntityType&, int, const MapLocation&, const Team&, int, py::object, int>(),
             py::arg("rtype"), py::arg("energy"), py::arg("location"), py::arg("team"),
             py::arg("cround"), py::arg("cplanet"), py::arg("rid"))
        .def_readwrite("info", &Entity::info)
        .def_readwrite("cooldown", &Entity::cooldown)
        .def_readwrite("created_round", &Entity::created_round)
        .def_readwrite("created_planet", &Entity::created_planet)
        .def("get_controller", &Entity::get_controller);

    // Engine functions
    m.def("engine_get_overdrive_factor", &engine_get_overdrive_factor,
          py::arg("overdrive_factor"), py::arg("team_tag"), py::arg("current_round"));
    m.def("engine_process_overdrive", &engine_process_overdrive,
          py::arg("entity_ids"), py::arg("entity_infos"), py::arg("attacker"),
          py::arg("radius"), py::arg("odfactor"));
    m.def("engine_compute_miner_income", &engine_compute_miner_income,
          py::arg("energy"));
    m.def("engine_process_charge", &engine_process_charge,
          py::arg("charge_list"), py::arg("charge_team_tags"));
    m.def("engine_check_round_end", &engine_check_round_end,
          py::arg("entity_ids"), py::arg("team_tags"), py::arg("type_names"),
          py::arg("created_rounds"), py::arg("current_round"));
}
